from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import DatabaseServer, ReplicationLink, ReplicationSetupLog, DatabaseUser # Import DatabaseUser
from django.core.exceptions import ObjectDoesNotExist
from .forms import DatabaseServerForm
import logging
import json
logger = logging.getLogger(__name__)

import mysql.connector
import time
from django.views.decorators.csrf import csrf_exempt
import secrets
import string
import tempfile
import os
import subprocess
from .utils import encrypt_data, decrypt_data # Import encryption utilities

try:
    from djsql.replication import MySQLReplicationHelper, ReplicationError
except ImportError:
    # For development/testing without MySQL
    class ReplicationError(Exception):
        def __init__(self, message, command_to_run=None):
            self.message = message
            self.command_to_run = command_to_run
            super().__init__(message)

    class MySQLReplicationHelper:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self):
            # This is a mock implementation for development/testing
            class MockCursor:
                def execute(self, query):
                    pass
                def fetchall(self):
                    return []
                def close(self):
                    pass
            class MockConnection:
                def cursor(self):
                    return MockCursor()
                def close(self):
                    pass
            return MockConnection()

        def check_slave_status(self):
            return {}

        def create_replication_user(self, username, password, host, privileges):
            pass

def generate_password(length=16):
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def test_connection(host, port, user, encrypted_password, timeout=5): # Renamed password to encrypted_password
    decrypted_password = decrypt_data(encrypted_password) # Decrypt password
    try:
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=decrypted_password, # Use decrypted password
            connection_timeout=timeout,
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci'
        )
        cursor = connection.cursor()
        
        try:
            cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
        except mysql.connector.Error as err:
            if err.errno == 1273:  # Unknown collation error
                cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_general_ci'")
        
        cursor.execute("SHOW VARIABLES WHERE Variable_name IN ('character_set_server', 'collation_server', 'version', 'version_comment')")
        vars = dict(cursor.fetchall())
        charset = vars.get('character_set_server', 'unknown')
        collation = vars.get('collation_server', 'unknown')
        version = vars.get('version', '')
        version_comment = vars.get('version_comment', '')
        
        logger.info(f"Server version info - Version: {version}, Comment: {version_comment}")
        full_version = f"{version} {version_comment}"
        
        cursor.close()
        connection.close()
        return True, None, charset, collation, full_version
    except mysql.connector.Error as err:
        error_msg = str(err)
        if err.errno == 1273:
            error_msg = (
                "Collation error. The server doesn't support utf8mb4_0900_ai_ci. "
                "Using fallback collation utf8mb4_general_ci"
            )
        return False, error_msg, None, None, None

def add_server(request):
    if request.method == 'POST':
        form = DatabaseServerForm(request.POST)
        if form.is_valid():
            try:
                # Encrypt password before testing connection and saving
                plain_password = form.cleaned_data['password']
                encrypted_password = encrypt_data(plain_password)
                
                is_connected, error, _, _, _ = test_connection(
                    form.cleaned_data['host'],
                    form.cleaned_data['port'],
                    form.cleaned_data['username'],
                    encrypted_password # Pass encrypted password to test_connection
                )
                
                if not is_connected:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Connection test failed: {error}'
                    })
                
                server = form.save(commit=False) # Don't save yet
                server.password = encrypted_password # Set encrypted password
                server.save() # Now save
                
                logger.debug(f"Server saved: {server}")
                return JsonResponse({
                    'status': 'success',
                    'server_id': server.id
                })
            except Exception as e:
                logger.exception(f"Exception saving server: {e}")
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                })
    logger.debug(f"Invalid request method: {request.method}")
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    })

def edit_server(request, server_id):
    try:
        server = DatabaseServer.objects.get(id=server_id)
        if request.method == 'POST':
            form = DatabaseServerForm(request.POST, instance=server)
            if form.is_valid():
                # Get current encrypted password
                old_encrypted_password = server.password
                
                # Get new password from form
                new_plain_password = form.cleaned_data['password']
                
                # Determine password to use for connection test and saving
                password_for_test = ""
                password_to_save = ""

                if new_plain_password:
                    # New password provided, encrypt it
                    password_to_save = encrypt_data(new_plain_password)
                    password_for_test = new_plain_password # Test with plain text before encryption
                else:
                    # Password field is empty, retain old encrypted password
                    password_to_save = old_encrypted_password
                    password_for_test = decrypt_data(old_encrypted_password) # Decrypt for test
                
                # Test connection if credentials changed
                # Note: form.cleaned_data['password'] will be the plain text if provided, or empty string
                # We need to compare with the *decrypted* old password for accurate change detection
                old_plain_password_for_comparison = decrypt_data(old_encrypted_password)

                if (form.cleaned_data['host'] != server.host or
                    form.cleaned_data['port'] != server.port or
                    form.cleaned_data['username'] != server.username or
                    new_plain_password != old_plain_password_for_comparison): # Compare plain text passwords
                    
                    is_connected, error, _, _, _ = test_connection(
                        form.cleaned_data['host'],
                        form.cleaned_data['port'],
                        form.cleaned_data['username'],
                        password_to_save # Pass the encrypted password to test_connection
                    )
                    
                    if not is_connected:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Connection test failed: {error}'
                        })
                
                server = form.save(commit=False) # Don't save yet
                server.password = password_to_save # Set the determined password (encrypted)
                server.save() # Now save
                
                return JsonResponse({
                    'status': 'success',
                    'server_id': server.id
                })
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid form data'
            })
    except DatabaseServer.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Server not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

def delete_server(request, server_id):
    if request.method == 'POST':
        try:
            server = DatabaseServer.objects.get(id=server_id)
            server.delete()
            return JsonResponse({
                'status': 'success'
            })
        except DatabaseServer.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Server not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    })

def djsql(request):
    if request.method == 'POST' and 'setup_replication' in request.POST:
        return redirect('djsql:setup_replication_step', step=1)
        
    servers = DatabaseServer.objects.all()
    server_statuses = {}
    
    # Test connection and check replication status for each server
    for server in servers:
        try:
            is_connected, error, charset, collation, version = test_connection(
                server.host,
                server.port,
                server.username,
                server.password # This is already encrypted
            )
            
            slave_status = None
            if is_connected:
                try:
                    helper = MySQLReplicationHelper(
                        server.host,
                        server.port,
                        server.username,
                        decrypt_data(server.password) # Decrypt password for helper
                    )
                    slave_status = helper.check_slave_status()
                    if not slave_status:
                        slave_status = {'is_error': True, 'Last_Error': 'No replication status found.'}
                    else:
                        # Determine if there's an error based on multiple conditions
                        is_io_sql_running = (slave_status.get('Slave_IO_Running') == 'Yes' and
                                             slave_status.get('Slave_SQL_Running') == 'Yes')
                        is_replicate_do_db_empty = (slave_status.get('Replicate_Do_DB') == '')

                        if not is_io_sql_running:
                            slave_status['is_error'] = True
                            slave_status['Last_Error'] = slave_status.get('Last_Error') or 'Replication IO or SQL thread is not running.'
                        elif is_replicate_do_db_empty:
                            slave_status['is_error'] = True
                            slave_status['Last_Error'] = slave_status.get('Last_Error') or 'Replication is active but no databases are configured for replication (Replicate_Do_DB is empty).'
                        else:
                            slave_status['is_error'] = False
                            slave_status['Last_Error'] = slave_status.get('Last_Error') or 'Replication is running correctly.'

                    if slave_status and 'Master_Host' in slave_status:
                        try:
                            master_host = slave_status['Master_Host']
                            master_port = int(slave_status['Master_Port'])
                            master_server = DatabaseServer.objects.get(host=master_host, port=master_port)
                            slave_status['master_server_name'] = master_server.name
                        except (DatabaseServer.DoesNotExist, KeyError, ValueError):
                            slave_status['master_server_name'] = None
                except Exception as e:
                    logger.warning(f"Failed to check slave status for {server.name}: {str(e)}")
            
            server_statuses[server.id] = {
                'connected': is_connected,
                'error': error,
                'charset': charset,
                'collation': collation,
                'version': version,
                'slave_status': slave_status
            }
        except Exception as e:
            server_statuses[server.id] = {
                'connected': False,
                'error': str(e),
                'charset': None,
                'collation': None,
                'version': None,
                'slave_status': None
            }
    
    # Show both active and pending replication links
    replications = ReplicationLink.objects.select_related('source', 'target').filter(
        status='active'
    )
    
    return render(request, 'djsql/djsql.html', {
        'title': 'SQL Replication Dashboard',
        'active_menu': 'djsql',
        'servers': servers,
        'server_statuses': server_statuses,
        'replications': replications
    })

def list_databases(request, server_id):
    try:
        server = DatabaseServer.objects.get(id=server_id)
        
        # First test the connection
        is_connected, error, charset, collation, version = test_connection(
            server.host, 
            server.port, 
            server.username, 
            server.password # This is already encrypted
        )
        if not is_connected:
            return JsonResponse({
                'status': 'error',
                'message': f'Connection failed: {error}'
            }, status=500)
        
        # If connection test passed, get databases
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=server.host,
                port=server.port,
                user=server.username,
                password=decrypt_data(server.password), # Decrypt password for connection
                connection_timeout=5,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
            
            cursor = connection.cursor()
            
            try:
                cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
            except mysql.connector.Error as err:
                if err.errno == 1273:  # Unknown collation error
                    cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_general_ci'")
                
            # Get list of databases
            cursor.execute("SHOW DATABASES")
            databases = [db[0] for db in cursor.fetchall() if db[0] not in ['information_schema', 'performance_schema', 'mysql', 'sys']]
            
            # Get server version
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            
            # Get server status
            cursor.execute("SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Uptime')")
            status_vars = dict(cursor.fetchall())
            
            # Get character set and collation information
            cursor.execute("SHOW VARIABLES WHERE Variable_name IN ('character_set_server', 'collation_server')")
            charset_vars = dict(cursor.fetchall())

            # Get slave status (replication info)
            helper = MySQLReplicationHelper(
                server.host,
                server.port,
                server.username,
                decrypt_data(server.password) # Decrypt password for helper
            )
            slave_status = helper.check_slave_status()

            return JsonResponse({
                'status': 'success',
                'databases': databases,
                'server_name': server.name,
                'version': version,
                'connected_threads': status_vars.get('Threads_connected', '0'),
                'uptime_seconds': status_vars.get('Uptime', '0'),
                'character_set': charset_vars.get('character_set_server', 'unknown'),
                'collation': charset_vars.get('collation_server', 'unknown'),
                'slave_status': slave_status
            })
            
        except mysql.connector.Error as err:
            error_message = f'Database error: {str(err)}'
            if err.errno == 1115:  # Specific error code for utf8mb4 issues
                error_message += (
                    ". The server doesn't support utf8mb4 character set. "
                    "To fix this, add the following to your MySQL server configuration:\n"
                    "[mysqld]\n"
                    "character-set-server = utf8mb4\n"
                    "collation-server = utf8mb4_unicode_ci"
                )
            return JsonResponse({
                'status': 'error',
                'message': error_message,
                'error_code': err.errno
            }, status=500)
        except Exception as e:
            # Catch any other unexpected errors and return a generic JSON error
            return JsonResponse({
                'status': 'error',
                'message': f'An unexpected error occurred during database operations: {str(e)}'
            }, status=500)
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    except DatabaseServer.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Server not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An unexpected error occurred: {str(e)}'
        }, status=500)

@csrf_exempt
def setup_replication_step(request, step):
    """Handle individual steps of the replication setup wizard"""
    
    rep_setup = request.session.get('replication_setup', {})
    
    if request.method == 'POST':
        try:
            # Handle both form data and JSON data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST
            
            logger.info(f"Step {step} - Action: {data.get('action')}")
            logger.info(f"Request data: {data}")
            logger.info(f"Content type: {request.content_type}")
            
            if step == 1:
                source_id = data.get('source')
                target_id = data.get('target')
                if not source_id or not target_id:
                    logger.error("Missing source or target server IDs")
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Source and target servers must be selected'
                    })
                if source_id == target_id:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Source and target servers cannot be the same'
                    })
                try:
                    source = DatabaseServer.objects.get(id=source_id)
                    target = DatabaseServer.objects.get(id=target_id)
                except DatabaseServer.DoesNotExist:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'One or both of the servers were not found'
                    })

                rep_setup = {
                    'source_id': source.id,
                    'target_id': target.id,
                    'setup_step': 1
                }
                request.session['replication_setup'] = rep_setup
                request.session.modified = True
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'Server selection saved'
                })
                
            elif step == 2:
                action = data.get('action')
                
                if action == 'select_sql_user':
                    server_id = data.get('server_id')
                    if not server_id:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Server ID is required'
                        })
                    
                    try:
                        server = DatabaseServer.objects.get(id=server_id)
                        helper = MySQLReplicationHelper(
                            server.host,
                            server.port,
                            server.username,
                            server.password
                        )
                        
                        # Get existing users
                        cursor = helper.connect().cursor()
                        try:
                            cursor.execute("SELECT User, Host FROM mysql.user")
                            users = cursor.fetchall()
                            
                            # Format users for response
                            user_list = [{'username': user[0], 'host': user[1]} for user in users]
                            
                            return JsonResponse({
                                'status': 'success',
                                'users': user_list
                            })
                        finally:
                            cursor.close()
                            
                    except DatabaseServer.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Server not found'
                        })
                    except mysql.connector.Error as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Database error: {str(e)}'
                        })
                
                elif action == 'check_grants':
                    server_id = data.get('server_id')
                    username = data.get('username')
                    host = data.get('host')
                    
                    if not all([server_id, username, host]):
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Missing required parameters'
                        })
                    
                    try:
                        server = DatabaseServer.objects.get(id=server_id)
                        helper = MySQLReplicationHelper(
                            server.host,
                            server.port,
                            server.username,
                            server.password
                        )

                        grants = helper.check_user_privileges(username, host)

                        return JsonResponse({
                            'status': 'success',
                            'grants': grants
                        })

                    except DatabaseServer.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Server not found'
                        })
                    except ReplicationError as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                    except mysql.connector.Error as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Database error: {str(e)}'
                        })


                elif action == 'execute_sql':
                    server_id = data.get('server_id')
                    sql_command = data.get('sql_command')
                    
                    if not all([server_id, sql_command]):
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Missing required parameters'
                        })
                    
                    try:
                        server = DatabaseServer.objects.get(id=server_id)
                        helper = MySQLReplicationHelper(
                            server.host,
                            server.port,
                            server.username,
                            server.password
                        )
                        
                        # Execute SQL command
                        cursor = helper.connect().cursor()
                        try:
                            cursor.execute(sql_command)
                            return JsonResponse({
                                'status': 'success',
                                'message': 'SQL command executed successfully',
                                'output': 'Privileges granted successfully'
                            })
                        finally:
                            cursor.close()
                            
                    except DatabaseServer.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Server not found'
                        })
                    except mysql.connector.Error as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })

                elif action == 'delete_sql_user':
                    server_id = data.get('server_id')
                    username = data.get('username')
                    host = data.get('host')
                    logger.info(f"Deleting SQL user {username}@{host} from server {server_id}")
                    
                    if not all([server_id, username, host]):
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Missing required parameters'
                        })
                    
                    try:
                        server = DatabaseServer.objects.get(id=server_id)
                        helper = MySQLReplicationHelper(
                            server.host,
                            server.port,
                            server.username,
                            server.password
                        )
                        
                        # Delete user
                        cursor = helper.connect().cursor()
                        try:
                            # Drop user if exists
                            drop_user_sql = f"DROP USER IF EXISTS '{username}'@'{host}'"
                            cursor.execute(drop_user_sql)
                            
                            # Flush privileges
                            cursor.execute("FLUSH PRIVILEGES")
                            
                            # Delete user from SQLite
                            DatabaseUser.objects.filter(
                                server_id=server_id,
                                username=username,
                                host=host
                            ).delete()
                            
                            return JsonResponse({
                                'status': 'success',
                                'message': 'User deleted successfully'
                            })
                        finally:
                            cursor.close()
                            
                    except DatabaseServer.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Server not found'
                        })
                    except mysql.connector.Error as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                elif action == 'create_sql_user':
                    server_id = data.get('server_id')
                    username = data.get('username')
                    password = data.get('password')
                    host = data.get('host') # Retrieve host from data
                    logging.info(f"Received data for create_sql_user: server_id={server_id}, username={username}, host={host}")

                    if not all([server_id, username, password, host]): # Add host to check
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Missing required parameters'
                        })

                    logging.info("Attempting to create replication user...")
                    try:
                        server = DatabaseServer.objects.get(id=server_id)
                        helper = MySQLReplicationHelper(
                            server.host,
                            server.port,
                            server.username,
                            decrypt_data(server.password) # Decrypt password for helper
                        )

                        # Create replication user with appropriate privileges
                        helper.create_replication_user(
                            username,
                            password,
                            host, # Use the retrieved host
                            privileges="REPLICATION SLAVE, REPLICATION CLIENT"
                        )

                        # Save user to local database
                        DatabaseUser.objects.update_or_create(
                            server=server,
                            username=username,
                            host=host,
                            defaults={'password': encrypt_data(password), 'user_type': 'repl'} # Encrypt password
                        )

                        return JsonResponse({
                            'status': 'success',
                            'message': 'User created successfully'
                        })

                    except Exception as e:
                        logging.error("Error creating replication user:", exc_info=True)
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                elif action == 'validate_prerequisites':
                    source_user = data.get('source_user')
                    target_user = data.get('target_user')
                    
                    logger.info(f"Validating prerequisites - Source user: {source_user}, Target user: {target_user}")
                    logger.info(f"Session before update: {request.session.get('replication_setup', {})}")
                    
                    if not source_user:
                        logger.error("Missing source or target user")
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Please select the source user before proceeding.'
                        })
                    
                    try:
                        source_username, source_host = source_user.split('@')
                        if target_user:
                            target_username, target_host = target_user.split('@')
                            logger.info(f"Parsed users - Source: {source_username}@{source_host}, Target: {target_username}@{target_host}")
                        else:
                            logger.info(f"Parsed users - Source: {source_username}@{source_host}")
                    except ValueError:
                        logger.error("Invalid user format")
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Invalid user format'
                        })
                    
                    try:
                        source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        target = DatabaseServer.objects.get(id=rep_setup['target_id'])
                        logger.info(f"Found servers - Source: {source.name}, Target: {target.name}")
                        
                        source_helper = MySQLReplicationHelper(
                            source.host,
                            source.port,
                            source.username,
                            decrypt_data(source.password) # Decrypt password for helper
                        )
                        target_helper = MySQLReplicationHelper(
                            target.host,
                            target.port,
                            target.username,
                            decrypt_data(target.password) # Decrypt password for helper
                        )
                    except DatabaseServer.DoesNotExist as e:
                        logger.error(f"Server not found: {str(e)}")
                        return JsonResponse({
                            'status': 'error',
                            'message': 'One or both servers not found'
                        })
                    
                    try:
                        # Check source user privileges
                        source_privs = source_helper.check_user_privileges(source_username, source_host)
                        logger.info(f"Source user privileges: {source_privs}")
                        if not all(priv in source_privs for priv in ['REPLICATION SLAVE', 'REPLICATION CLIENT']):
                            logger.error("Source user missing required privileges")
                            return JsonResponse({
                                'status': 'error',
                                'message': 'Selected source user is missing required privileges'
                            })
                        
                        # Check target user privileges
                        if target_user:
                            target_privs = target_helper.check_user_privileges(target_username, target_host)
                            logger.info(f"Target user privileges: {target_privs}")
                            if 'REPLICATION CLIENT' not in target_privs:
                                logger.error("Target user missing required privileges")
                                return JsonResponse({
                                    'status': 'error',
                                    'message': 'Selected target user is missing required privileges'
                                })
                    except Exception as e:
                        logger.error(f"Error checking privileges: {str(e)}")
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Error checking privileges: {str(e)}'
                        })
                    
                    try:
                        # Save user selections to session
                        rep_setup['source_user'] = source_user
                        if target_user:
                            rep_setup['target_user'] = target_user
                        rep_setup['setup_step'] = 2  # Update step progress
                        request.session['replication_setup'] = rep_setup
                        request.session.modified = True
                        logger.info("Session updated with user selections")
                        logger.info(f"Updated session data: {rep_setup}")
                        
                        # Force session save
                        request.session.save()
                        
                        response_data = {
                            'status': 'success',
                            'message': 'Prerequisites check passed',
                            'next_step': '/djsql/replication/setup/3/'
                        }
                        logger.info(f"Sending response: {response_data}")
                        return JsonResponse(response_data)
                    except Exception as e:
                        logger.error(f"Error saving to session: {str(e)}")
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Error saving selections: {str(e)}'
                        })
            elif step == 3:
                action = data.get('action')
                
                if action == 'get_master_status':
                    database = data.get('database')
                    if not database:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Database name is required'
                        })
                    
                    try:
                        source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        source_helper = MySQLReplicationHelper(
                            source.host,
                            source.port,
                            source.username,
                            source.password
                        )
                        
                        # Check binary logging
                        cursor = source_helper.connect().cursor()
                        cursor.execute("SHOW VARIABLES LIKE 'log_bin'")
                        log_bin = cursor.fetchone()
                        if not log_bin or log_bin[1].lower() != 'on':
                            raise ReplicationError("Binary logging is not enabled on source server")
                        
                        # Get master status
                        master_status = source_helper.get_master_status()
                        
                        return JsonResponse({
                            'status': 'success',
                            'master_status': master_status
                        })
                        
                    except (DatabaseServer.DoesNotExist, ReplicationError) as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                
                elif action == 'generate_commands':
                    database = data.get('database')
                    if not database:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Database name is required'
                        })
                    
                    try:
                        source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        target = DatabaseServer.objects.get(id=rep_setup['target_id'])
                        
                        # Get source master status
                        source_helper = MySQLReplicationHelper(
                            source.host,
                            source.port,
                            source.username,
                            source.password
                        )
                        master_status = source_helper.get_master_status()
                        
                        # Get replication user credentials
                        source_user, source_host = rep_setup['source_user'].split('@')
                        db_user = DatabaseUser.objects.get(
                            server=source,
                            username=source_user,
                            host=source_host
                        )
                        
                        # Generate source commands (for backup) as single line
                        source_commands = f"-- On source server ({source.name}) -- Get master status for replication SHOW MASTER STATUS; -- Lock tables for consistent backup FLUSH TABLES WITH READ LOCK;"
                        
                        # Generate target commands (for replication setup) as single line without comments
                        target_commands = (
                            f"STOP SLAVE; RESET SLAVE; "
                            f"CREATE DATABASE IF NOT EXISTS `{database}`; "
                            f"CHANGE MASTER TO MASTER_HOST='{source.host}', MASTER_PORT={source.port}, "
                            f"MASTER_USER='{db_user.username}', MASTER_PASSWORD='{db_user.password}', "
                            f"MASTER_LOG_FILE='{master_status['file']}', MASTER_LOG_POS={master_status['position']}; "
                            f"START SLAVE; SHOW SLAVE STATUS;"
                        )
                        
                        return JsonResponse({
                            'status': 'success',
                            'source_commands': source_commands.strip(),
                            'target_commands': target_commands.strip(),
                            'database': database
                        })
                        
                    except Exception as e:
                        logger.error(f"Error generating commands: {str(e)}")
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Error generating commands: {str(e)}'
                        })
                    
                    try:
                        source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        target = DatabaseServer.objects.get(id=rep_setup['target_id'])
                        
                        source_user_full = rep_setup['source_user']
                        source_user, source_host = source_user_full.split('@')
                        
                        logger.info(f"Source server ID: {source.id}")
                        logger.info(f"Source server name: {source.name}")
                        logger.info(f"Looking for user: {source_user}@{source_host}")
                        
                        # Get all matching users for debugging
                        all_users = DatabaseUser.objects.filter(username=source_user)
                        for user in all_users:
                            logger.info(f"Found user in DB - Server: {user.server.name} (ID: {user.server.id}), User: {user.username}@{user.host}, Password length: {len(user.password)}")
                        
                        # Get the source user's password from DatabaseUser
                        try:
                            # First check if there's an existing replication link with this password
                            existing_link = ReplicationLink.objects.filter(
                                source=source,
                                replication_user=source_user,
                                status='active'
                            ).first()
                            
                            if existing_link and existing_link.replication_password:
                                logger.info("Found password in existing replication link")
                                repl_password = existing_link.replication_password
                            else:
                                # Get password from DatabaseUser
                                source_db_user = DatabaseUser.objects.get(
                                    server=source,
                                    username=source_user,
                                    host=source_host
                                )
                                logger.info(f"Retrieved user from correct server - Server: {source_db_user.server.name} (ID: {source_db_user.server.id})")
                                logger.info(f"User details - {source_db_user.username}@{source_db_user.host}")
                                logger.info(f"Password from DatabaseUser: {source_db_user.password}")
                                repl_password = source_db_user.password
                        except DatabaseUser.DoesNotExist:
                            logger.error(f"DatabaseUser not found for {source_user}@{source_host} on server {source.name} (ID: {source.id})")
                            return JsonResponse({
                                'status': 'error',
                                'message': f'Replication user {source_user}@{source_host} not found in database'
                            })
                        
                        # Execute commands on target server
                        try:
                            target_helper = MySQLReplicationHelper(
                                target.host,
                                target.port,
                                target.username,
                                target.password
                            )
                            
                            target_helper.setup_slave(
                                source.host,
                                source.port,
                                source_user,
                                repl_password,
                                master_status['file'],
                                master_status['position'],
                                databases=[database]
                            )
                            
                            # Also update the replication link object
                            repl_link, created = ReplicationLink.objects.get_or_create(
                                source=source,
                                target=target,
                                defaults={
                                    'databases': [database],
                                    'status': 'active',
                                    'replication_user': source_user,
                                    'replication_password': repl_password,
                                    'server_id_source': 1,
                                    'server_id_target': 2,
                                    'setup_step': 4,
                                    'setup_data': {
                                        'master_log_file': master_status['file'],
                                        'master_log_pos': master_status['position']
                                    }
                                }
                            )

                            if not created:
                                # If the link already existed, add the new database if it's not already there
                                if database not in repl_link.databases:
                                    repl_link.databases.append(database)
                                    repl_link.save()
                            
                            # Verify replication status
                            slave_status = target_helper.check_slave_status()
                            if not slave_status or slave_status.get('Slave_IO_Running') != 'Yes' or slave_status.get('Slave_SQL_Running') != 'Yes':
                                raise ReplicationError("Replication failed to start properly")
                            
                            return JsonResponse({
                                'status': 'success',
                                'message': 'Replication setup completed successfully',
                                'slave_status': slave_status
                            })
                            
                        except Exception as e:
                            logger.error(f"Error executing replication commands: {str(e)}")
                            return JsonResponse({
                                'status': 'error',
                                'message': f'Replication setup failed: {str(e)}',
                                'debug': str(e)
                            })
                        master_commands = [
                            f"-- On source server ({source.name})",
                            f"-- First, ensure binary logging is enabled",
                            f"SHOW VARIABLES LIKE 'log_bin';",
                            f"",
                            f"-- Create replication database if not exists",
                            f"CREATE DATABASE IF NOT EXISTS `{database}`;",
                            f"",
                            f"-- Lock tables to get consistent snapshot",
                            f"FLUSH TABLES WITH READ LOCK;",
                            f"SHOW MASTER STATUS;"
                        ]
                        
                        # Get master status from session if available
                        master_status = rep_setup.get('master_status', {})
                        master_log_file = master_status.get('file', '<from_show_master_status>')
                        master_log_pos = master_status.get('position', '<from_show_master_status>')

                        # Commands for target server with master status values (using placeholders if not available)
                        slave_commands = [
                            f"-- On target server ({target.name})",
                            f"-- Stop and reset any existing replication",
                            f"STOP SLAVE;",
                            f"RESET SLAVE;",
                            f"",
                            f"-- Create database if not exists",
                            f"CREATE DATABASE IF NOT EXISTS `{database}`;",
                            f"",
                            f"-- Configure replication",
                            f"CHANGE MASTER TO",
                            f"    MASTER_HOST='{source.host}',",
                            f"    MASTER_PORT={source.port},",
                            f"    MASTER_USER='{source_user}',",
                            f"    MASTER_PASSWORD='{repl_password}',",  # Use password from DatabaseUser
                            f"    MASTER_LOG_FILE='{master_log_file}',",
                            f"    MASTER_LOG_POS={master_log_pos};",
                            f"",
                            f"-- Start replication",
                            f"START SLAVE;",
                            f"SHOW SLAVE STATUS"
                        ]
                        
                        # Debug log the commands
                        logger.info("Generated slave commands:")
                        for cmd in slave_commands:
                            logger.info(cmd)
                        logger.info(f"Using replication password: {repl_password}")
                        
                        return JsonResponse({
                            'status': 'success',
                            'master_commands': master_commands,
                            'slave_commands': slave_commands
                        })
                        
                    except DatabaseServer.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Server not found'
                        })
                        
                elif action == 'execute_command':
                    database = data.get('database')
                    server = data.get('server')
                    command = data.get('command')
                    
                    if not all([database, server, command]):
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Database, server and command are required'
                        })
                        
                    try:
                        if server == 'source':
                            db_server = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        elif server == 'target':
                            db_server = DatabaseServer.objects.get(id=rep_setup['target_id'])
                        else:
                            return JsonResponse({
                                'status': 'error',
                                'message': 'Invalid server type'
                            })
                            
                        helper = MySQLReplicationHelper(
                            db_server.host,
                            db_server.port,
                            db_server.username,
                            db_server.password
                        )
                        
                        # Execute commands
                        cursor = helper.connect().cursor()
                        
                        # Split commands and execute each one
                        commands = command.split(';')
                        results = []
                        
                        for cmd in commands:
                            cmd = cmd.strip()
                            if not cmd or cmd.startswith('--'):  # Skip empty lines and comments
                                continue
                                
                            try:
                                logger.info(f"Executing command: {cmd}")
                                cursor.execute(cmd)
                                
                                if cursor.description:  # If command returns results
                                    rows = cursor.fetchall()
                                    if rows:
                                        # Format the results
                                        columns = [col[0] for col in cursor.description]
                                        
                                        # Special handling for SHOW SLAVE STATUS
                                        if cmd.upper().strip().endswith('SLAVE STATUS'):
                                            # Convert to key-value pairs
                                            formatted_rows = []
                                            for row in rows:
                                                for i, col in enumerate(columns):
                                                    formatted_rows.append([col, str(row[i])])
                                            results.append({
                                                'command': cmd,
                                                'rows': formatted_rows,
                                                'columns': ['Variable', 'Value']
                                            })
                                        else:
                                            results.append({
                                                'command': cmd,
                                                'rows': rows,
                                                'columns': columns
                                            })
                            except mysql.connector.Error as e:
                                raise ReplicationError(f"Error executing '{cmd}': {str(e)}")
                        
                        # If this is source server, get and store master status
                        master_status = None
                        if server == 'source':
                            cursor.execute("SHOW MASTER STATUS")
                            status = cursor.fetchone()
                            if status:
                                master_status = {
                                    'file': status[0],
                                    'position': status[1],
                                    'binlog_do_db': status[2],
                                    'binlog_ignore_db': status[3]
                                }
                                rep_setup['master_status'] = master_status
                                request.session['replication_setup'] = rep_setup
                                request.session.modified = True
                                request.session.save()  # Force save the session
                                
                                # Log the master status for debugging
                                logger.info(f"Saved master status to session: {master_status}")
                                request.session.save()  # Force save the session
                                
                                # Log the master status for debugging
                                logger.info(f"Saved master status to session: {master_status}")
                        
                        cursor.close()
                        
                        response_data = {
                            'status': 'success',
                            'message': f'Commands executed successfully on {server} server',
                            'results': results
                        }
                        
                        if master_status:
                            response_data['master_status'] = master_status
                            
                        return JsonResponse(response_data)
                        
                    except (DatabaseServer.DoesNotExist, ReplicationError) as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                        
                elif action == 'execute_slave_commands':
                    database = data.get('database')
                    
                    # First get master status from session
                    master_status = rep_setup.get('master_status')
                    if not master_status:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Master status not found. Please execute source commands first.'
                        })
                    
                    master_log_file = master_status.get('file')
                    master_log_pos = master_status.get('position')
                    
                    if not all([database, master_log_file, master_log_pos]):
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Missing required parameters. Make sure source commands were executed successfully.'
                        })
                    
                    try:
                        source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        target = DatabaseServer.objects.get(id=rep_setup['target_id'])
                        source_user_full = rep_setup['source_user']
                        source_user, source_host = source_user_full.split('@')
                        
                        # Get the source user's password from DatabaseUser
                        source_db_user = DatabaseUser.objects.get(
                            server=source,
                            username=source_user,
                            host=source_host
                        )
                        
                        target_helper = MySQLReplicationHelper(
                            target.host,
                            target.port,
                            target.username,
                            target.password
                        )
                        
                        # Decrypt the replication user's password before passing it to setup_slave
                        decrypted_repl_password = decrypt_data(source_db_user.password)

                        target_helper.setup_slave(
                            source.host,
                            source.port,
                            source_user,
                            decrypted_repl_password, # Pass the decrypted password
                            master_log_file,
                            master_log_pos,
                            databases=[database]
                        )
                        
                        return JsonResponse({
                            'status': 'success',
                            'message': 'Slave commands executed successfully'
                        })
                        
                    except (DatabaseServer.DoesNotExist, ReplicationError) as e:
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                        
                elif action == 'transfer_data':
                    database = data.get('database')
                    if not database:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Database selection is required'
                        })
                        
                    try:
                        source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                        target = DatabaseServer.objects.get(id=rep_setup['target_id'])
                        
                        # Connect to source server
                        source_conn = mysql.connector.connect(
                            host=source.host,
                            port=source.port,
                            user=source.username,
                            password=source.password,
                            database=database,
                            charset='utf8mb4',
                            collation='utf8mb4_general_ci'  # Use a more compatible collation
                        )
                        source_cursor = source_conn.cursor()
                        
                        # Connect to target server
                        target_conn = mysql.connector.connect(
                            host=target.host,
                            port=target.port,
                            user=target.username,
                            password=target.password,
                            charset='utf8mb4',
                            collation='utf8mb4_general_ci'  # Use a more compatible collation
                        )
                        target_cursor = target_conn.cursor()
                        
                        try:
                            # Create database on target if it doesn't exist with compatible collation
                            target_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
                            target_cursor.execute(f"USE `{database}`")
                            target_cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
                            
                            # Get table list from source
                            source_cursor.execute("SHOW TABLES")
                            tables = source_cursor.fetchall()
                            
                            # For each table
                            for table in tables:
                                table_name = table[0]
                                
                                # Get create table statement
                                source_cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
                                create_stmt = source_cursor.fetchone()[1]
                                
                                # Replace MySQL 8 specific collations with compatible ones
                                create_stmt = create_stmt.replace('utf8mb4_0900_ai_ci', 'utf8mb4_general_ci')
                                create_stmt = create_stmt.replace('utf8mb4_0900_as_ci', 'utf8mb4_general_ci')
                                create_stmt = create_stmt.replace('utf8mb4_0900_as_cs', 'utf8mb4_general_ci')
                                create_stmt = create_stmt.replace('utf8mb4_0900_bin', 'utf8mb4_bin')
                                
                                # Create table on target
                                target_cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
                                target_cursor.execute(create_stmt)
                                
                                # Get data
                                source_cursor.execute(f"SELECT * FROM `{table_name}`")
                                rows = source_cursor.fetchall()
                                
                                if rows:
                                    # Get column information
                                    columns = [i[0] for i in source_cursor.description]
                                    placeholders = ', '.join(['%s'] * len(columns))
                                    
                                    # Insert data in batches
                                    batch_size = 1000
                                    for i in range(0, len(rows), batch_size):
                                        batch = rows[i:i + batch_size]
                                        target_cursor.executemany(
                                            f"INSERT INTO `{table_name}` VALUES ({placeholders})",
                                            batch
                                        )
                                
                                target_conn.commit()
                            
                            # Transfer routines (stored procedures, functions)
                            source_cursor.execute("""
                                SELECT ROUTINE_TYPE, ROUTINE_NAME, ROUTINE_DEFINITION
                                FROM information_schema.ROUTINES
                                WHERE ROUTINE_SCHEMA = %s
                            """, (database,))
                            
                            routines = source_cursor.fetchall()
                            for routine_type, routine_name, routine_def in routines:
                                target_cursor.execute(f"DROP {routine_type} IF EXISTS `{routine_name}`")
                                target_cursor.execute(routine_def)
                            
                            # Transfer triggers
                            source_cursor.execute("""
                                SELECT TRIGGER_NAME, ACTION_STATEMENT, ACTION_TIMING, EVENT_MANIPULATION
                                FROM information_schema.TRIGGERS
                                WHERE EVENT_OBJECT_SCHEMA = %s
                            """, (database,))
                            
                            triggers = source_cursor.fetchall()
                            for trigger_name, action_stmt, timing, event in triggers:
                                target_cursor.execute(f"DROP TRIGGER IF EXISTS `{trigger_name}`")
                                target_cursor.execute(f"""
                                    CREATE TRIGGER `{trigger_name}`
                                    {timing} {event}
                                    {action_stmt}
                                """)
                            
                            target_conn.commit()
                            target_cursor.execute("SET FOREIGN_KEY_CHECKS=1;")
                            
                            return JsonResponse({
                                'status': 'success',
                                'message': 'Database transferred successfully',
                                'details': f'Transferred {len(tables)} tables, {len(routines)} routines, {len(triggers)} triggers'
                            })
                            
                        finally:
                            source_cursor.close()
                            target_cursor.close()
                            source_conn.close()
                            target_conn.close()
                            
                    except Exception as e:
                        # Ensure tables are unlocked even if there's an error
                        try:
                            source_cursor.execute("UNLOCK TABLES")
                        except:
                            pass  # Ignore any errors during unlock
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
                        
                elif action == 'save_selection':
                    database = data.get('database')
                    if not database:
                        return JsonResponse({
                            'status': 'error',
                            'message': 'Database selection is required'
                        })
                    
                    rep_setup['selected_database'] = database
                    request.session['replication_setup'] = rep_setup
                    request.session.modified = True
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Database selection saved'
                    })
                    
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Unknown action'
                    })
                    
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON data'
            })
            
    # GET request handling
    if step == 1:
        servers = DatabaseServer.objects.all()
        server_statuses = {}
        
        for server in servers:
            try:
                is_connected, error, charset, collation, version = test_connection(
                    server.host,
                    server.port,
                    server.username,
                    server.password
                )
                server_statuses[server.id] = {
                    'connected': is_connected,
                    'error': error,
                    'charset': charset,
                    'collation': collation,
                    'version': version
                }
            except Exception as e:
                logger.error(f"Connection test failed for server {server.id}: {str(e)}")
                server_statuses[server.id] = {
                    'connected': False,
                    'error': str(e),
                    'charset': None,
                    'collation': None,
                    'version': None
                }
        
        return render(request, 'djsql/wizard/step1_servers.html', {
            'title': 'Setup Replication - Select Servers',
            'active_menu': 'djsql',
            'servers': servers,
            'server_statuses': server_statuses
        })
        
    elif step == 2:
        if not rep_setup.get('source_id') or not rep_setup.get('target_id'):
            return redirect('djsql:setup_replication_step', step=1)
            
        try:
            source = DatabaseServer.objects.get(id=rep_setup['source_id'])
            target = DatabaseServer.objects.get(id=rep_setup['target_id'])
            
            source_helper = MySQLReplicationHelper(
                source.host,
                source.port,
                source.username,
                source.password
            )
            target_helper = MySQLReplicationHelper(
                target.host,
                target.port,
                target.username,
                target.password
            )
            
            source_users = []
            target_users = []
            excluded_users = ['healthcheck', 'mariadb.sys']
            
            source_required_privs = [
                'REPLICATION SLAVE',
                'REPLICATION CLIENT',
                'RELOAD'
            ]
            target_required_privs = [
                'REPLICATION CLIENT',
                'SUPER',
                'RELOAD'
            ]
            
            source_version = None
            target_version = None
            source_type = None
            target_type = None
            
            def get_server_type(version_str):
                logger.info(f"Raw version string: {version_str}")
                if version_str:
                    is_mariadb = any(x in version_str.lower() for x in ['mariadb', '-maria-', '-mariadb-'])
                    return "MariaDB" if is_mariadb else "MySQL"
                return None
            
            try:
                _, _, _, _, source_version = test_connection(source.host, source.port, source.username, source.password)
                source_type = get_server_type(source_version)
                logger.info(f"Source type determined as: {source_type}")
            except Exception as e:
                logger.error(f"Error getting source version: {str(e)}")
                
            try:
                _, _, _, _, target_version = test_connection(target.host, target.port, target.username, target.password)
                target_type = get_server_type(target_version)
            except Exception as e:
                logger.error(f"Error getting target version: {str(e)}")
            
            try:
                source_cursor = source_helper.connect().cursor()
                source_cursor.execute("SELECT user, host FROM mysql.user")
                source_users = [
                    {'user': user, 'host': host} 
                    for user, host in source_cursor.fetchall()
                    if user not in excluded_users
                ]
                
                # Check if user is created via the app (stored in DatabaseUser model)
                for usr in source_users:
                    usr['app_created'] = DatabaseUser.objects.filter(
                        server=source,
                        username=usr['user'],
                        host=usr['host']
                    ).exists()
                    try:
                        grants = source_helper.check_user_privileges(usr['user'], usr['host'])
                        usr['grants'] = grants
                        mapped_grants = set(grants)
                        if 'BINLOG MONITOR' in grants:
                            mapped_grants.add('REPLICATION CLIENT')
                        usr['sufficient'] = all(priv in mapped_grants for priv in source_required_privs)
                        usr['available_privs'] = list(mapped_grants)
                    except Exception as e:
                        usr['grants'] = []
                        usr['sufficient'] = False
                        usr['available_privs'] = []
                
                source_cursor.close()
            except Exception as e:
                source_error = str(e)
                logger.error("Error getting source server info: %s", str(e))
            
            try:
                target_cursor = target_helper.connect().cursor()
                target_cursor.execute("SELECT user, host FROM mysql.user")
                target_users = [
                    {'user': user, 'host': host} 
                    for user, host in target_cursor.fetchall()
                    if user not in excluded_users
                ]
                
                # Check if user is created via the app (stored in DatabaseUser model)
                for usr in target_users:
                    usr['app_created'] = DatabaseUser.objects.filter(
                        server=target,
                        username=usr['user'],
                        host=usr['host']
                    ).exists()
                    try:
                        grants = target_helper.check_user_privileges(usr['user'], usr['host'])
                        usr['grants'] = grants
                        mapped_grants = set(grants)
                        if 'BINLOG MONITOR' in grants:
                            mapped_grants.add('REPLICATION CLIENT')
                        usr['sufficient'] = all(priv in mapped_grants for priv in target_required_privs)
                        usr['available_privs'] = list(mapped_grants)
                    except Exception as e:
                        usr['grants'] = []
                        usr['sufficient'] = False
                        usr['available_privs'] = []
                
                target_cursor.close()
            except Exception as e:
                target_error = str(e)
                logger.error("Error getting target server info: %s", str(e))
            
            return render(request, 'djsql/wizard/step2_prerequisites.html', {
                'title': 'Setup Replication - Prerequisites Check',
                'active_menu': 'djsql',
                'source': {
                    'name': source.name,
                    'users': source_users,
                    'server_id': source.id,
                    'required_privs': source_required_privs,
                    'version': source_version,
                    'type': source_type
                },
                'target': {
                    'name': target.name,
                    'users': target_users,
                    'server_id': target.id,
                    'required_privs': target_required_privs,
                    'version': target_version,
                    'type': target_type
                }
            })
            
        except DatabaseServer.DoesNotExist:
            return redirect('djsql:setup_replication_step', step=1)
            
    elif step == 3:
        # Verify previous steps are completed
        if not rep_setup.get('source_id') or not rep_setup.get('target_id'):
            return redirect('djsql:setup_replication_step', step=1)
        if not rep_setup.get('source_user') or rep_setup.get('setup_step', 0) < 2:
            return redirect('djsql:setup_replication_step', step=2)
            
        try:
            source = DatabaseServer.objects.get(id=rep_setup['source_id'])
            target = DatabaseServer.objects.get(id=rep_setup['target_id'])
            
            source_helper = MySQLReplicationHelper(
                source.host,
                source.port,
                source.username,
                source.password
            )
            
            source_cursor = source_helper.connect().cursor()
            logger.info("Fetching source databases...")
            source_cursor.execute("""
                SELECT 
                    table_schema as 'name',
                    COALESCE(ROUND(SUM(COALESCE(data_length, 0) + COALESCE(index_length, 0)) / 1024 / 1024, 2), 0) as 'size',
                    COUNT(table_name) as 'tables'
                FROM information_schema.tables
                WHERE table_schema NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
                GROUP BY table_schema
            """)
            results = source_cursor.fetchall()
            logger.info(f"Found {len(results)} source databases")
            source_databases = [
                {
                    'name': row[0],
                    'size': f"{row[1]} MB",
                    'tables': row[2]
                }
                for row in results
            ]
            logger.info(f"Source databases: {source_databases}")
            source_cursor.close()
            
            target_helper = MySQLReplicationHelper(
                target.host,
                target.port,
                target.username,
                target.password
            )
            
            target_cursor = target_helper.connect().cursor()
            logger.info("Fetching target databases...")
            target_cursor.execute("SHOW DATABASES")
            results = target_cursor.fetchall()
            logger.info(f"Found {len(results)} target databases")
            target_databases = [
                db[0] for db in results
                if db[0] not in ['information_schema', 'performance_schema', 'mysql', 'sys']
            ]
            logger.info(f"Target databases: {target_databases}")
            target_cursor.close()
            
            # Get replication users
            source_user = rep_setup.get('source_user', '').split('@')[0] if rep_setup.get('source_user') else None
            target_user = rep_setup.get('target_user', '').split('@')[0] if rep_setup.get('target_user') else None
            
            # Get replication users with hosts
            source_user_full = rep_setup.get('source_user', '')
            target_user_full = rep_setup.get('target_user', '')
            
            # Extract user and host parts
            source_user = source_user_full.split('@')[0] if source_user_full else None
            source_host_part = source_user_full.split('@')[1] if source_user_full and '@' in source_user_full else None
            target_user = target_user_full.split('@')[0] if target_user_full else None
            target_host_part = target_user_full.split('@')[1] if target_user_full and '@' in target_user_full else None
            
            return render(request, 'djsql/wizard/step3_databases.html', {
                'title': 'Setup Replication - Select Databases',
                'active_menu': 'djsql',
                'source': {
                    'name': source.name,
                    'host': source.host,
                    'port': source.port,
                    'repl_user': source_user,
                    'repl_host': source_host_part,
                    'databases': source_databases
                },
                'target': {
                    'name': target.name,
                    'host': target.host,
                    'port': target.port,
                    'repl_user': target_user,
                    'repl_host': target_host_part,
                    'databases': target_databases
                },
                'selected_database': rep_setup.get('selected_database')
            })
            
        except DatabaseServer.DoesNotExist:
            return redirect('djsql:setup_replication_step', step=1)
            
    elif step == 4:
        if not rep_setup.get('source_id') or not rep_setup.get('target_id'):
            return redirect('djsql:setup_replication_step', step=1)
            
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                if data.get('action') == 'create_replication_link':
                    source = DatabaseServer.objects.get(id=rep_setup['source_id'])
                    target = DatabaseServer.objects.get(id=rep_setup['target_id'])
                    database_name = rep_setup.get('selected_database')

                    # Get the source user's password
                    source_user_full = rep_setup.get('source_user', '')
                    source_user, source_host = source_user_full.split('@')
                    
                    try:
                        source_db_user = DatabaseUser.objects.get(
                            server=source,
                            username=source_user,
                            host=source_host
                        )
                        
                        # Try to get an existing link, or create a new one
                        repl_link, created = ReplicationLink.objects.get_or_create(
                            source=source,
                            target=target,
                            defaults={
                                'databases': [database_name],
                                'status': 'active',
                                'replication_user': source_user,
                                'replication_password': source_db_user.password,
                                'server_id_source': 1,
                                'server_id_target': 2,
                                'setup_step': 4,
                                'setup_data': {
                                    'master_log_file': rep_setup.get('master_status', {}).get('file'),
                                    'master_log_pos': rep_setup.get('master_status', {}).get('position')
                                }
                            }
                        )

                        if not created:
                            # If the link already existed, add the new database if it's not already there
                            if database_name not in repl_link.databases:
                                repl_link.databases.append(database_name)
                                repl_link.save()
                                
                                # Also update the replication filter on the server
                                helper = MySQLReplicationHelper(
                                    repl_link.target.host,
                                    repl_link.target.port,
                                    repl_link.target.username,
                                    repl_link.target.password
                                )
                                _, _, _, _, version_info = test_connection(
                                    repl_link.target.host,
                                    repl_link.target.port,
                                    repl_link.target.username,
                                    repl_link.target.password
                                )
                                is_mariadb = 'mariadb' in version_info.lower()

                                cursor = helper.connect().cursor()
                                cursor.execute("STOP SLAVE")
                                if is_mariadb:
                                    db_list_str = ','.join(repl_link.databases)
                                    filter_sql = f"SET GLOBAL replicate_do_db = '{db_list_str}'"
                                else:
                                    db_list_str = ', '.join(f"'{db}'" for db in repl_link.databases)
                                    filter_sql = f"CHANGE REPLICATION FILTER REPLICATE_DO_DB = ({db_list_str})"
                                
                                logger.info(f"Updating replication filter for {'MariaDB' if is_mariadb else 'MySQL'}: {filter_sql}")
                                cursor.execute(filter_sql)
                                cursor.execute("START SLAVE")
                                cursor.close()
                        
                    except DatabaseUser.DoesNotExist:
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Replication user {source_user}@{source_host} not found in database'
                        })
                    
                    # Clear the session data
                    request.session.pop('replication_setup', None)
                    
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Replication link created successfully'
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                })
            
        try:
            source = DatabaseServer.objects.get(id=rep_setup['source_id'])
            target = DatabaseServer.objects.get(id=rep_setup['target_id'])
            
            # Get master status from session
            master_status = rep_setup.get('master_status', {})
            source_user = rep_setup.get('source_user', '').split('@')[0]
            target_user = rep_setup.get('target_user', '').split('@')[0]
            
            return render(request, 'djsql/wizard/step4_user.html', {
                'title': 'Setup Replication - Overview',
                'active_menu': 'djsql',
                'source': source,
                'target': target,
                'source_user': source_user,
                'target_user': target_user,
                'databases': [rep_setup.get('selected_database')],
                'master_log_file': master_status.get('file'),
                'master_log_pos': master_status.get('position')
            })
            
        except DatabaseServer.DoesNotExist:
            return redirect('djsql:setup_replication_step', step=1)
    
    return redirect('djsql:setup_replication_step', step=1)

@csrf_exempt
def replication_status(request, link_id):
    """Get replication status and logs"""
    try:
        repl_link = ReplicationLink.objects.get(id=link_id)
        logs = ReplicationSetupLog.objects.filter(replication=repl_link).order_by('-timestamp')[:5]
        
        # Get slave status from target server
        slave_status = None
        try:
            helper = MySQLReplicationHelper(
                repl_link.target.host,
                repl_link.target.port,
                repl_link.target.username,
                repl_link.target.password
            )
            slave_status = helper.check_slave_status()
            
            # Calculate replication lag if available
            lag_seconds = None
            if slave_status and 'Seconds_Behind_Master' in slave_status:
                lag_seconds = slave_status['Seconds_Behind_Master']
                if lag_seconds == '':
                    lag_seconds = None
                elif lag_seconds is not None:
                    lag_seconds = int(lag_seconds)
            
            # Format the response to match what the frontend expects
            response_data = {
                'status': 'success',
                'replication': {
                    'status': repl_link.status,
                    'error_message': repl_link.error_message,
                    'setup_step': repl_link.setup_step,
                    'lag_seconds': lag_seconds,
                    'databases': repl_link.databases,
                    'user': repl_link.replication_user,
                    'slave_status': slave_status,
                    'source': {
                        'host': repl_link.source.host,
                        'port': repl_link.source.port
                    },
                    'target': {
                        'host': repl_link.target.host,
                        'port': repl_link.target.port
                    },
                    'binlog_info': {
                        'file': repl_link.setup_data.get('master_log_file') if repl_link.setup_data else None
                    }
                },
                'logs': [
                    {
                        'timestamp': log.timestamp.isoformat(),
                        'step': log.step,
                        'status': log.status,
                        'message': log.message,
                        'is_error': log.is_error,
                        'command_to_run': log.command_to_run
                    }
                    for log in logs
                ]
            }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            logger.error(f"Error getting replication status: {str(e)}", exc_info=True)
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
            
    except ReplicationLink.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Replication link not found'
        }, status=404)
    except ReplicationLink.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Replication link not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
def delete_replication(request, link_id):
    """Delete a replication link"""
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'Only POST method is allowed'
        }, status=405)
        
    try:
        repl_link = ReplicationLink.objects.get(id=link_id)
        
        if repl_link.status == 'active':
            try:
                target_helper = MySQLReplicationHelper(
                    repl_link.target.host,
                    repl_link.target.port,
                    repl_link.target.username,
                    repl_link.target.password
                )
                
                target_helper.clean_slave()
                
            except Exception as e:
                logger.error(f"Error cleaning replica during deletion: {str(e)}")
                # Don't prevent deletion if cleaning fails, but log it
                pass
        
        repl_link.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Replication link deleted successfully'
        })
        
    except ReplicationLink.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Replication link not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error deleting replication: {str(e)}'
        }, status=500)


@csrf_exempt
def clean_replica(request, server_id):
    """Stop and reset a replica"""
    if request.method == 'POST':
        try:
            server = DatabaseServer.objects.get(id=server_id)
            helper = MySQLReplicationHelper(
                server.host,
                server.port,
                server.username,
                server.password
            )
            success, message = helper.clean_slave()
            if success:
                return JsonResponse({'status': 'success', 'message': message})
            else:
                return JsonResponse({'status': 'error', 'message': message}, status=500)
        except DatabaseServer.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Server not found'}, status=404)
        except ReplicationError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
def unlink_database(request, link_id):
    """Unlink a specific database from a replication link"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
        db_name = data.get('database')
        if not db_name:
            return JsonResponse({'status': 'error', 'message': 'Database name is required'}, status=400)

        repl_link = ReplicationLink.objects.get(id=link_id)

        if db_name not in repl_link.databases:
            return JsonResponse({'status': 'error', 'message': 'Database not found in this replication link'}, status=404)

        # Create a copy of the list before modifying
        original_databases = list(repl_link.databases)
        repl_link.databases.remove(db_name)
        repl_link.save()

        try:
            helper = MySQLReplicationHelper(
                repl_link.target.host,
                repl_link.target.port,
                repl_link.target.username,
                repl_link.target.password
            )
            
            # Check if the target server is MariaDB
            _, _, _, _, version_info = test_connection(
                repl_link.target.host,
                repl_link.target.port,
                repl_link.target.username,
                repl_link.target.password
            )
            is_mariadb = 'mariadb' in version_info.lower()

            # Construct the appropriate command
            cursor = helper.connect().cursor()
            cursor.execute("STOP SLAVE")

            if is_mariadb:
                # MariaDB uses SET GLOBAL for replication filters
                db_list_str = ','.join(repl_link.databases)
                filter_sql = f"SET GLOBAL replicate_do_db = '{db_list_str}'"
                if not repl_link.databases:
                    filter_sql = "SET GLOBAL replicate_do_db = ''"
            else:
                # MySQL uses CHANGE REPLICATION FILTER
                if repl_link.databases:
                    db_list_str = ', '.join(f"'{db}'" for db in repl_link.databases)
                    filter_sql = f"CHANGE REPLICATION FILTER REPLICATE_DO_DB = ({db_list_str})"
                else:
                    filter_sql = "CHANGE REPLICATION FILTER REPLICATE_DO_DB = ()"

            logger.info(f"Executing replication filter change for {'MariaDB' if is_mariadb else 'MySQL'}: {filter_sql}")
            cursor.execute(filter_sql)
            cursor.execute("START SLAVE")
            cursor.close()

            return JsonResponse({'status': 'success', 'message': f'Database {db_name} unlinked successfully.'})

        except Exception as e:
            # If updating the server fails, revert the change in the Django database
            repl_link.databases = original_databases
            repl_link.save()
            logger.error(f"Failed to update replication filter on target server: {str(e)}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': f'Failed to update replication on target server: {str(e)}'}, status=500)

    except ReplicationLink.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Replication link not found'}, status=404)
    except Exception as e:
        logger.error(f"Error unlinking database: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
