import os
import json
import poplib
import smtplib
import email
import base64
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import parseaddr, formatdate, make_msgid, parsedate_to_datetime
from email.header import decode_header
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import Email, EmailAttachment, EmailFolder

def connect_to_pop3(account):
    """Connect to POP3 server and return connection object"""
    if account.use_ssl:
        connection = poplib.POP3_SSL(account.pop3_server, account.pop3_port)
    else:
        connection = poplib.POP3(account.pop3_server, account.pop3_port)
    
    connection.user(account.username)
    connection.pass_(account.password)
    
    return connection

def connect_to_smtp(account):
    """Connect to SMTP server and return connection object"""
    if account.use_ssl:
        connection = smtplib.SMTP_SSL(account.smtp_server, account.smtp_port)
    else:
        connection = smtplib.SMTP(account.smtp_server, account.smtp_port)
        connection.starttls()
    
    connection.login(account.username, account.password)
    
    return connection

def decode_email_header(header_text):
    """Decode email header to handle various encodings"""
    if not header_text:
        return ""
    
    decoded_parts = []
    parts = decode_header(header_text)
    
    for part, encoding in parts:
        if isinstance(part, bytes):
            try:
                if encoding:
                    decoded_parts.append(part.decode(encoding or 'utf-8', errors='replace'))
                else:
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            except:
                decoded_parts.append(part.decode('utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    
    return ''.join(decoded_parts)

def get_email_body(message):
    """
    Extract plain text and HTML body from email message
    Returns a tuple of (body_text, body_html)
    """
    body_text = ""
    body_html = ""
    
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
                
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(charset, errors="replace")
                except Exception as e:
                    print(f"Error decoding text/plain: {e}")
                    body_text = "Error decoding message"
                    
            if content_type == "text/html" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_html = payload.decode(charset, errors="replace")
                except Exception as e:
                    print(f"Error decoding text/html: {e}")
                    body_html = "<p>Error decoding HTML message</p>"
    else:
        # Not multipart - get the content type and payload
        content_type = message.get_content_type()
        payload = message.get_payload(decode=True)
        
        try:
            charset = message.get_content_charset() or 'utf-8'
            if payload:
                decoded = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    body_text = decoded
                elif content_type == "text/html":
                    body_html = decoded
        except Exception as e:
            print(f"Error decoding message body: {e}")
            body_text = "Error decoding message"
    
    return body_text, body_html

def extract_sender_info(from_header):
    """Extract sender name and email from From header"""
    if not from_header:
        return "", ""
    
    name, email_addr = parseaddr(from_header)
    name = decode_email_header(name)
    
    return name, email_addr

def fetch_emails(account, limit=20, folder_type='inbox'):
    """
    Fetch emails from POP3 server
    Returns a list of saved Email objects
    """
    connection = connect_to_pop3(account)
    
    # Get mailbox status
    status = connection.stat()
    num_messages = status[0]
    
    # Get inbox folder or create if not exists
    folder, created = EmailFolder.objects.get_or_create(
        account=account,
        folder_type=folder_type,
        defaults={
            'name': folder_type.capitalize(),
            'is_system': True
        }
    )
    
    saved_emails = []
    
    # Fetch the latest emails up to the limit
    start = max(1, num_messages - limit + 1)
    end = num_messages + 1
    
    for i in range(start, end):
        try:
            # Get message
            msg_data = connection.retr(i)
            raw_message = b'\n'.join(msg_data[1])
            parsed_message = email.message_from_bytes(raw_message)
            
            # Get unique ID to prevent duplicates
            uid = connection.uidl(i).split()[1].decode()
            
            # Check if email already exists
            if Email.objects.filter(account=account, uid=uid).exists():
                continue
            
            # Parse headers
            subject = decode_email_header(parsed_message['Subject'])
            sender_name, sender_email = extract_sender_info(parsed_message['From'])
            recipients = parsed_message['To'] or ""
            cc = parsed_message['Cc'] or ""
            date_str = parsed_message['Date']
            
            # Parse date
            try:
                date_received = parsedate_to_datetime(date_str)
            except:
                date_received = timezone.now()
            
            # Get message ID
            message_id = parsed_message['Message-ID']
            
            # Get body content
            body_text, body_html = get_email_body(parsed_message)
            
            # Calculate message size
            size = len(raw_message)
            
            # Create Email object
            email_obj = Email.objects.create(
                account=account,
                folder=folder,
                message_id=message_id,
                subject=subject,
                sender=sender_email,
                sender_name=sender_name,
                recipients=recipients,
                cc=cc,
                body_text=body_text,
                body_html=body_html,
                date_received=date_received,
                size=size,
                uid=uid
            )
            
            # Process attachments
            for part in parsed_message.walk():
                content_disposition = part.get("Content-Disposition", "")
                if "attachment" in content_disposition:
                    filename = decode_email_header(part.get_filename())
                    if not filename:
                        continue
                    
                    content_type = part.get_content_type()
                    payload = part.get_payload(decode=True)
                    
                    if payload:
                        attachment_size = len(payload)
                        
                        # Create attachment
                        attachment = EmailAttachment(
                            email=email_obj,
                            filename=filename,
                            content_type=content_type,
                            size=attachment_size
                        )
                        
                        # Save file content
                        attachment.file.save(
                            filename,
                            ContentFile(payload),
                            save=True
                        )
            
            saved_emails.append(email_obj)
            
        except Exception as e:
            print(f"Error processing message {i}: {e}")
    
    connection.quit()
    return saved_emails

def send_email(account, to_emails, subject, body_text, body_html=None, cc_emails=None, bcc_emails=None, attachments=None):
    """
    Send email via SMTP
    Returns a tuple of (success, error_message)
    """
    try:
        if not to_emails:
            return False, "No recipients specified"
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['From'] = account.email
        msg['To'] = to_emails if isinstance(to_emails, str) else ', '.join(to_emails)
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid(domain=account.email.split('@')[1])
        
        # Add CC and BCC if specified
        if cc_emails:
            msg['Cc'] = cc_emails if isinstance(cc_emails, str) else ', '.join(cc_emails)
            
        # Add text part
        part1 = MIMEText(body_text, 'plain')
        msg.attach(part1)
        
        # Add HTML part if provided
        if body_html:
            part2 = MIMEText(body_html, 'html')
            msg.attach(part2)
        
        # Add attachments if any
        if attachments:
            for attachment in attachments:
                filename = os.path.basename(attachment.name)
                attachment_data = attachment.read()
                
                part = MIMEApplication(attachment_data)
                part.add_header('Content-Disposition', 'attachment', filename=filename)
                msg.attach(part)
        
        # Connect to SMTP server and send
        connection = connect_to_smtp(account)
        
        # Prepare recipient list (including CC and BCC)
        all_recipients = []
        if isinstance(to_emails, str):
            all_recipients.append(to_emails)
        else:
            all_recipients.extend(to_emails)
            
        if cc_emails:
            if isinstance(cc_emails, str):
                all_recipients.append(cc_emails)
            else:
                all_recipients.extend(cc_emails)
                
        if bcc_emails:
            if isinstance(bcc_emails, str):
                all_recipients.append(bcc_emails)
            else:
                all_recipients.extend(bcc_emails)
        
        # Send email
        connection.sendmail(account.email, all_recipients, msg.as_string())
        connection.quit()
        
        # Save to sent folder
        folder, created = EmailFolder.objects.get_or_create(
            account=account,
            folder_type='sent',
            defaults={
                'name': 'Sent',
                'is_system': True
            }
        )
        
        # Create sent email object
        email_obj = Email.objects.create(
            account=account,
            folder=folder,
            message_id=msg['Message-ID'],
            subject=subject,
            sender=account.email,
            sender_name="",
            recipients=msg['To'],
            cc=msg.get('Cc', ""),
            bcc=bcc_emails if isinstance(bcc_emails, str) else (', '.join(bcc_emails) if bcc_emails else ""),
            body_text=body_text,
            body_html=body_html or "",
            date_received=timezone.now(),
            read=True,  # Sent emails are already read
            size=len(msg.as_string())
        )
        
        return True, ""
    except Exception as e:
        return False, str(e)
