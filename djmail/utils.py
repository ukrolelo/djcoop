import os
import json
import poplib
import smtplib
import email
import base64
import datetime
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import parseaddr, formatdate, make_msgid, parsedate_to_datetime
from email.header import decode_header
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from .models import Email, EmailAttachment, EmailFolder, EmailAccount
from .email_logger import get_email_logger, EmailOperationTimer
from djsql.utils import decrypt_data

def connect_to_pop3(account):
    """Connect to POP3 server and return connection object"""
    if account.use_ssl:
        connection = poplib.POP3_SSL(account.pop3_server, account.pop3_port)
    else:
        connection = poplib.POP3(account.pop3_server, account.pop3_port)

    # Decrypt password before using it
    decrypted_password = decrypt_data(account.password)
    connection.user(account.username)
    connection.pass_(decrypted_password)

    return connection

def connect_to_smtp(account):
    """Connect to SMTP server and return connection object"""
    if account.use_ssl:
        connection = smtplib.SMTP_SSL(account.smtp_server, account.smtp_port)
    else:
        connection = smtplib.SMTP(account.smtp_server, account.smtp_port)
        connection.starttls()

    # Decrypt password before using it
    decrypted_password = decrypt_data(account.password)
    connection.login(account.username, decrypted_password)

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
    from .mail_logger import get_mail_logger

    # Initialize logger for this fetch operation
    logger = get_mail_logger("POP3_FETCH")

    try:
        logger.fetch_connection(account.pop3_server, account.pop3_port, account.use_ssl, True)
        connection = connect_to_pop3(account)

        # Get mailbox status
        status = connection.stat()
        num_messages = status[0]

        logger.info(f"Connected to mailbox",
                   server=account.pop3_server,
                   total_messages=num_messages)
    except Exception as e:
        logger.fetch_connection(account.pop3_server, account.pop3_port, account.use_ssl, False, str(e))
        raise
    
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
    new_emails_count = 0

    # Fetch the latest emails up to the limit
    start = max(1, num_messages - limit + 1)
    end = num_messages + 1

    logger.info(f"Processing messages",
               range_start=start,
               range_end=end-1,
               limit=limit)

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
                logger.info(f"Skipping duplicate email", message_id=uid, position=i)
                continue

            new_emails_count += 1
            
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
            logger.info(f"Saved new email",
                       subject=subject[:50],
                       sender=sender_email,
                       message_id=uid)

        except Exception as e:
            logger.error(f"Failed to process email",
                        position=i,
                        error=e)
            print(f"Error processing message {i}: {e}")

    connection.quit()

    # Log final results
    logger.fetch_messages(num_messages, new_emails_count, len(saved_emails))
    logger.fetch_complete()

    return saved_emails

def send_email(account, to_emails, subject, body_text, body_html=None, cc_emails=None, bcc_emails=None, attachments=None, user=None):
    """
    Send email via SMTP with comprehensive logging
    Returns a tuple of (success, error_message)
    """
    from .mail_logger import get_mail_logger

    # Initialize loggers
    db_logger = get_email_logger(email_account=account, user=user)
    mail_logger = get_mail_logger("SMTP_SEND")
    start_time = time.time()

    # Log send start
    mail_logger.send_start(subject, to_emails, account.email)

    try:
        if not to_emails:
            error_msg = "No recipients specified"
            db_logger.log_email_send(
                subject=subject,
                from_email=account.email,
                to_email=str(to_emails),
                success=False,
                error_msg=error_msg
            )
            mail_logger.send_complete(success=False, error=error_msg)
            return False, error_msg
        
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
        db_logger.log_system_event(f"Preparing to send email: '{subject}' to {msg['To']}")
        connection = connect_to_smtp_with_logging(account, db_logger, mail_logger)
        
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
        
        # Create email object in Outbox folder first (before sending)
        outbox_folder, created = EmailFolder.objects.get_or_create(
            account=account,
            folder_type='outbox',
            defaults={
                'name': 'Outbox',
                'is_system': True
            }
        )

        email_obj = Email.objects.create(
            account=account,
            folder=outbox_folder,
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
            read=True,
            size=len(msg.as_string())
        )

        # Send email with timing
        send_start = time.time()
        db_logger.log_smtp_command(f"MAIL FROM:<{account.email}>")
        db_logger.log_smtp_command(f"RCPT TO:<{', '.join(all_recipients)}>")
        db_logger.log_smtp_command("DATA")

        connection.sendmail(account.email, all_recipients, msg.as_string())
        connection.quit()

        send_duration = int((time.time() - send_start) * 1000)
        mail_logger.info(f"Email sent successfully",
                        recipients=len(all_recipients),
                        duration_ms=send_duration)

        # Move email from Outbox to Sent folder after successful sending
        sent_folder, created = EmailFolder.objects.get_or_create(
            account=account,
            folder_type='sent',
            defaults={
                'name': 'Sent',
                'is_system': True
            }
        )

        email_obj.folder = sent_folder
        email_obj.save()

        # Log successful email send
        total_duration = int((time.time() - start_time) * 1000)
        db_logger.log_email_send(
            email_obj=email_obj,
            success=True,
            duration_ms=total_duration
        )
        mail_logger.send_complete(success=True, duration_seconds=total_duration/1000)

        return True, ""
    except Exception as e:
        # If email object was created but sending failed, it stays in Outbox
        # If email object wasn't created yet, create it in Outbox
        if 'email_obj' not in locals():
            # Create email object in Outbox folder for failed send
            outbox_folder, created = EmailFolder.objects.get_or_create(
                account=account,
                folder_type='outbox',
                defaults={
                    'name': 'Outbox',
                    'is_system': True
                }
            )

            email_obj = Email.objects.create(
                account=account,
                folder=outbox_folder,
                message_id=msg['Message-ID'] if 'msg' in locals() else f"failed-{int(time.time())}@{account.email}",
                subject=subject,
                sender=account.email,
                sender_name="",
                recipients=str(to_emails),
                cc=str(cc_emails) if cc_emails else "",
                bcc=str(bcc_emails) if bcc_emails else "",
                body_text=body_text,
                body_html=body_html or "",
                date_received=timezone.now(),
                read=True,
                size=len(body_text) if body_text else 0
            )

        # Log failed email send
        total_duration = int((time.time() - start_time) * 1000)
        db_logger.log_email_send(
            email_obj=email_obj,
            success=False,
            error_msg=str(e),
            duration_ms=total_duration
        )
        mail_logger.send_complete(success=False, error=str(e), duration_seconds=total_duration/1000)
        return False, str(e)


def connect_to_smtp_with_logging(account, db_logger, mail_logger=None):
    """
    Connect to SMTP server with comprehensive logging
    """
    if mail_logger is None:
        from .mail_logger import get_mail_logger
        mail_logger = get_mail_logger("SMTP_CONNECT")

    try:
        # Log connection attempt
        db_logger.log_smtp_connection(
            host=account.smtp_server,
            port=account.smtp_port,
            success=False  # Will update if successful
        )
        mail_logger.send_smtp_connection(account.smtp_server, account.smtp_port, account.smtp_port == 465, False)

        # Connect to server
        if account.smtp_port == 465:
            # SSL connection
            connection = smtplib.SMTP_SSL(account.smtp_server, account.smtp_port)
            db_logger.log_smtp_command("CONNECT (SSL)", "Connected via SSL", duration_ms=0)
            mail_logger.info("SSL connection established", server=account.smtp_server, port=account.smtp_port)
        else:
            # Regular connection, then STARTTLS
            connection = smtplib.SMTP(account.smtp_server, account.smtp_port)
            db_logger.log_smtp_command("CONNECT", "Connected", duration_ms=0)
            mail_logger.info("SMTP connection established", server=account.smtp_server, port=account.smtp_port)

            if account.smtp_port == 587:
                connection.starttls()
                db_logger.log_smtp_command("STARTTLS", "TLS enabled", duration_ms=0)
                mail_logger.info("TLS encryption enabled")

        # Update connection log to success
        db_logger.log_smtp_connection(
            host=account.smtp_server,
            port=account.smtp_port,
            success=True
        )
        mail_logger.send_smtp_connection(account.smtp_server, account.smtp_port, account.smtp_port == 465, True)

        # Authenticate
        if account.username and account.password:
            try:
                # Decrypt password
                from djsql.utils import decrypt_data
                decrypted_password = decrypt_data(account.password)

                auth_start = time.time()
                connection.login(account.username, decrypted_password)
                auth_duration = int((time.time() - auth_start) * 1000)

                db_logger.log_smtp_auth(
                    username=account.username,
                    success=True
                )
                db_logger.log_smtp_command(
                    f"AUTH LOGIN {account.username}",
                    "Authentication successful",
                    duration_ms=auth_duration,
                    success=True
                )
                mail_logger.send_smtp_auth(account.username, True)
            except Exception as auth_error:
                db_logger.log_smtp_auth(
                    username=account.username,
                    success=False,
                    error_msg=str(auth_error)
                )
                mail_logger.send_smtp_auth(account.username, False, str(auth_error))
                raise auth_error

        return connection

    except Exception as e:
        db_logger.log_smtp_connection(
            host=account.smtp_server,
            port=account.smtp_port,
            success=False,
            error_msg=str(e)
        )
        mail_logger.send_smtp_connection(account.smtp_server, account.smtp_port, account.smtp_port == 465, False, str(e))
        raise e
