"""
Mail Operations Logger

Provides specialized logging for different mail operations:
- mail_operations: General mail operations (sending, fetching, etc.)
- mail_errors: Mail operation errors and failures
- mail_fetch: Detailed mail fetching operations
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any

# Get specialized loggers
operations_logger = logging.getLogger('mail_operations')
errors_logger = logging.getLogger('mail_errors')
fetch_logger = logging.getLogger('mail_fetch')


class MailOperationsLogger:
    """Logger for mail operations with structured output"""
    
    def __init__(self, operation_type: str = "MAIL", session_id: Optional[str] = None):
        self.operation_type = operation_type
        self.session_id = session_id or self._generate_session_id()
        self.start_time = time.time()
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID for tracking related operations"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _format_message(self, message: str, **kwargs) -> str:
        """Format log message with session ID and additional context"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_parts = []
        
        if kwargs:
            for key, value in kwargs.items():
                if value is not None:
                    context_parts.append(f"{key}={value}")
        
        context_str = f" | {' | '.join(context_parts)}" if context_parts else ""
        return f"[{self.session_id}] {self.operation_type}: {message}{context_str}"
    
    def info(self, message: str, **kwargs):
        """Log general information"""
        operations_logger.info(self._format_message(message, **kwargs))
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log errors"""
        if error:
            kwargs['error_type'] = type(error).__name__
            kwargs['error_details'] = str(error)
        errors_logger.error(self._format_message(message, **kwargs))
    
    def fetch_start(self, account_email: str, server: str, folder: str = "INBOX"):
        """Log start of mail fetching operation"""
        fetch_logger.info(self._format_message(
            f"Starting mail fetch from {server}",
            account=account_email,
            folder=folder,
            operation="FETCH_START"
        ))
    
    def fetch_connection(self, server: str, port: int, ssl: bool, success: bool, error: Optional[str] = None):
        """Log mail server connection attempt"""
        status = "SUCCESS" if success else "FAILED"
        message = f"Connection to {server}:{port} ({'SSL' if ssl else 'Plain'}) - {status}"
        
        if success:
            fetch_logger.info(self._format_message(message, operation="CONNECT"))
        else:
            fetch_logger.error(self._format_message(message, error=error, operation="CONNECT"))
    
    def fetch_auth(self, username: str, success: bool, error: Optional[str] = None):
        """Log authentication attempt"""
        status = "SUCCESS" if success else "FAILED"
        message = f"Authentication for {username} - {status}"
        
        if success:
            fetch_logger.info(self._format_message(message, operation="AUTH"))
        else:
            fetch_logger.error(self._format_message(message, error=error, operation="AUTH"))
    
    def fetch_folder_select(self, folder: str, message_count: Optional[int] = None, success: bool = True):
        """Log folder selection"""
        if success:
            fetch_logger.info(self._format_message(
                f"Selected folder '{folder}'",
                message_count=message_count,
                operation="SELECT_FOLDER"
            ))
        else:
            fetch_logger.error(self._format_message(
                f"Failed to select folder '{folder}'",
                operation="SELECT_FOLDER"
            ))
    
    def fetch_messages(self, total_messages: int, new_messages: int, processed: int):
        """Log message fetching results"""
        fetch_logger.info(self._format_message(
            f"Processed {processed} messages",
            total_on_server=total_messages,
            new_messages=new_messages,
            operation="FETCH_MESSAGES"
        ))
    
    def fetch_complete(self, duration_seconds: Optional[float] = None):
        """Log completion of fetch operation"""
        if duration_seconds is None:
            duration_seconds = time.time() - self.start_time
        
        fetch_logger.info(self._format_message(
            "Mail fetch completed",
            duration_seconds=f"{duration_seconds:.2f}",
            operation="FETCH_COMPLETE"
        ))
    
    def send_start(self, subject: str, to_emails: list, from_email: str):
        """Log start of email sending"""
        operations_logger.info(self._format_message(
            f"Starting email send: '{subject}'",
            to=','.join(to_emails),
            from_email=from_email,
            operation="SEND_START"
        ))
    
    def send_smtp_connection(self, server: str, port: int, ssl: bool, success: bool, error: Optional[str] = None):
        """Log SMTP connection"""
        status = "SUCCESS" if success else "FAILED"
        message = f"SMTP connection to {server}:{port} ({'SSL' if ssl else 'Plain'}) - {status}"
        
        if success:
            operations_logger.info(self._format_message(message, operation="SMTP_CONNECT"))
        else:
            operations_logger.error(self._format_message(message, error=error, operation="SMTP_CONNECT"))
    
    def send_smtp_auth(self, username: str, success: bool, error: Optional[str] = None):
        """Log SMTP authentication"""
        status = "SUCCESS" if success else "FAILED"
        message = f"SMTP authentication for {username} - {status}"
        
        if success:
            operations_logger.info(self._format_message(message, operation="SMTP_AUTH"))
        else:
            operations_logger.error(self._format_message(message, error=error, operation="SMTP_AUTH"))
    
    def send_complete(self, success: bool, error: Optional[str] = None, duration_seconds: Optional[float] = None):
        """Log completion of email sending"""
        if duration_seconds is None:
            duration_seconds = time.time() - self.start_time
        
        status = "SUCCESS" if success else "FAILED"
        message = f"Email send completed - {status}"
        
        if success:
            operations_logger.info(self._format_message(
                message,
                duration_seconds=f"{duration_seconds:.2f}",
                operation="SEND_COMPLETE"
            ))
        else:
            operations_logger.error(self._format_message(
                message,
                error=error,
                duration_seconds=f"{duration_seconds:.2f}",
                operation="SEND_COMPLETE"
            ))
    
    def account_operation(self, operation: str, account_email: str, details: Optional[str] = None):
        """Log account-related operations"""
        operations_logger.info(self._format_message(
            f"Account operation: {operation}",
            account=account_email,
            details=details,
            operation="ACCOUNT"
        ))
    
    def folder_operation(self, operation: str, folder: str, email_count: Optional[int] = None):
        """Log folder operations"""
        operations_logger.info(self._format_message(
            f"Folder operation: {operation}",
            folder=folder,
            email_count=email_count,
            operation="FOLDER"
        ))


def get_mail_logger(operation_type: str = "MAIL", session_id: Optional[str] = None) -> MailOperationsLogger:
    """Get a mail operations logger instance"""
    return MailOperationsLogger(operation_type, session_id)


def log_mail_operation(operation: str, details: str, **kwargs):
    """Quick logging function for simple operations"""
    logger = get_mail_logger(operation)
    logger.info(details, **kwargs)


def log_mail_error(operation: str, error_message: str, error: Optional[Exception] = None, **kwargs):
    """Quick logging function for errors"""
    logger = get_mail_logger(operation)
    logger.error(error_message, error=error, **kwargs)
