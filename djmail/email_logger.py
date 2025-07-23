"""
Email logging utilities for tracking server communications
"""
import logging
import time
import uuid
from typing import Optional, Dict, Any
from django.contrib.auth.models import User
from .models import EmailAccount, Email, EmailServerLog

# Set up loggers
email_logger = logging.getLogger('djmail.email')
smtp_logger = logging.getLogger('djmail.smtp')


class EmailServerLogger:
    """Utility class for logging email server communications"""
    
    def __init__(self, email_account: Optional[EmailAccount] = None, user: Optional[User] = None):
        self.email_account = email_account
        self.user = user
        self.session_id = str(uuid.uuid4())[:8]  # Short session ID
        
    def log_smtp_connection(self, host: str, port: int, success: bool = True, error_msg: str = None):
        """Log SMTP connection attempt"""
        status = 'success' if success else 'error'
        message = f"SMTP connection to {host}:{port}"
        
        if success:
            message += " - Connected successfully"
            smtp_logger.info(f"[{self.session_id}] {message}")
        else:
            message += f" - Failed: {error_msg}"
            smtp_logger.error(f"[{self.session_id}] {message}")
        
        EmailServerLog.objects.create(
            log_type='smtp_connect',
            status=status,
            email_account=self.email_account,
            user=self.user,
            server_host=host,
            server_port=port,
            protocol='SMTP',
            message=message,
            error_message=error_msg or '',
            session_id=self.session_id,
            details={
                'connection_type': 'smtp',
                'success': success
            }
        )
    
    def log_smtp_auth(self, username: str, success: bool = True, error_msg: str = None):
        """Log SMTP authentication attempt"""
        status = 'success' if success else 'error'
        message = f"SMTP authentication for {username}"
        
        if success:
            message += " - Authenticated successfully"
            smtp_logger.info(f"[{self.session_id}] {message}")
        else:
            message += f" - Failed: {error_msg}"
            smtp_logger.error(f"[{self.session_id}] {message}")
        
        EmailServerLog.objects.create(
            log_type='smtp_auth',
            status=status,
            email_account=self.email_account,
            user=self.user,
            protocol='SMTP',
            message=message,
            error_message=error_msg or '',
            session_id=self.session_id,
            details={
                'username': username,
                'success': success
            }
        )
    
    def log_smtp_command(self, command: str, response: str = None, response_code: str = None, 
                        duration_ms: int = None, success: bool = True):
        """Log SMTP command and response"""
        status = 'success' if success else 'error'
        message = f"SMTP Command: {command}"
        
        if response:
            message += f" | Response: {response}"
        
        log_type = 'smtp_command' if success else 'smtp_error'
        
        smtp_logger.debug(f"[{self.session_id}] {message} (took {duration_ms}ms)")
        
        EmailServerLog.objects.create(
            log_type=log_type,
            status=status,
            email_account=self.email_account,
            user=self.user,
            protocol='SMTP',
            command=command,
            response=response or '',
            response_code=response_code or '',
            message=message,
            duration_ms=duration_ms,
            session_id=self.session_id,
            details={
                'command_type': 'smtp',
                'success': success
            }
        )
    
    def log_email_send(self, email_obj: Email = None, subject: str = None, 
                      from_email: str = None, to_email: str = None, 
                      success: bool = True, error_msg: str = None, duration_ms: int = None):
        """Log email sending operation"""
        status = 'success' if success else 'error'
        
        # Get email details from email object or parameters
        if email_obj:
            subject = email_obj.subject
            from_email = email_obj.sender
            to_email = email_obj.recipients
        
        message = f"Email sent: '{subject}' from {from_email} to {to_email}"
        
        if success:
            email_logger.info(f"[{self.session_id}] {message} (took {duration_ms}ms)")
        else:
            message += f" - Failed: {error_msg}"
            email_logger.error(f"[{self.session_id}] {message}")
        
        EmailServerLog.objects.create(
            log_type='send',
            status=status,
            email_account=self.email_account,
            user=self.user,
            email=email_obj,
            subject=subject or '',
            from_email=from_email or '',
            to_email=to_email or '',
            protocol='SMTP',
            message=message,
            error_message=error_msg or '',
            duration_ms=duration_ms,
            session_id=self.session_id,
            details={
                'operation': 'send_email',
                'success': success
            }
        )
    
    def log_imap_connection(self, host: str, port: int, success: bool = True, error_msg: str = None):
        """Log IMAP connection attempt"""
        status = 'success' if success else 'error'
        message = f"IMAP connection to {host}:{port}"
        
        if success:
            message += " - Connected successfully"
            email_logger.info(f"[{self.session_id}] {message}")
        else:
            message += f" - Failed: {error_msg}"
            email_logger.error(f"[{self.session_id}] {message}")
        
        EmailServerLog.objects.create(
            log_type='imap_connect',
            status=status,
            email_account=self.email_account,
            user=self.user,
            server_host=host,
            server_port=port,
            protocol='IMAP',
            message=message,
            error_message=error_msg or '',
            session_id=self.session_id,
            details={
                'connection_type': 'imap',
                'success': success
            }
        )
    
    def log_imap_command(self, command: str, response: str = None, 
                        duration_ms: int = None, success: bool = True):
        """Log IMAP command and response"""
        status = 'success' if success else 'error'
        message = f"IMAP Command: {command}"
        
        if response:
            message += f" | Response: {response[:200]}..."  # Truncate long responses
        
        log_type = 'imap_command' if success else 'imap_error'
        
        email_logger.debug(f"[{self.session_id}] {message} (took {duration_ms}ms)")
        
        EmailServerLog.objects.create(
            log_type=log_type,
            status=status,
            email_account=self.email_account,
            user=self.user,
            protocol='IMAP',
            command=command,
            response=response or '',
            message=message,
            duration_ms=duration_ms,
            session_id=self.session_id,
            details={
                'command_type': 'imap',
                'success': success
            }
        )
    
    def log_system_event(self, message: str, details: Dict[str, Any] = None, 
                        status: str = 'info', error_msg: str = None):
        """Log general system events"""
        email_logger.info(f"[{self.session_id}] SYSTEM: {message}")
        
        EmailServerLog.objects.create(
            log_type='system',
            status=status,
            email_account=self.email_account,
            user=self.user,
            message=message,
            error_message=error_msg or '',
            session_id=self.session_id,
            details=details or {}
        )


def get_email_logger(email_account: EmailAccount = None, user: User = None) -> EmailServerLogger:
    """Factory function to create an EmailServerLogger instance"""
    return EmailServerLogger(email_account=email_account, user=user)


class EmailOperationTimer:
    """Context manager for timing email operations"""
    
    def __init__(self, logger: EmailServerLogger, operation_name: str):
        self.logger = logger
        self.operation_name = operation_name
        self.start_time = None
        self.duration_ms = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        self.duration_ms = int((end_time - self.start_time) * 1000)
        
        if exc_type is None:
            self.logger.log_system_event(
                f"{self.operation_name} completed successfully",
                details={'duration_ms': self.duration_ms},
                status='success'
            )
        else:
            self.logger.log_system_event(
                f"{self.operation_name} failed",
                details={'duration_ms': self.duration_ms, 'error': str(exc_val)},
                status='error',
                error_msg=str(exc_val)
            )
    
    @property
    def duration(self):
        return self.duration_ms
