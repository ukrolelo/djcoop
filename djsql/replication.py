import mysql.connector
from mysql.connector import Error
import logging

logger = logging.getLogger(__name__)

class ReplicationError(Exception):
    def __init__(self, message, command_to_run=None):
        self.message = message
        self.command_to_run = command_to_run
        super().__init__(message)

class MySQLReplicationHelper:
    def __init__(self, host, port, user, password):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self._connection = None

    def connect(self):
        """Establish a connection to MySQL server"""
        if self._connection and self._connection.is_connected():
            logger.debug("Reusing existing MySQL connection")
            return self._connection

        try:
            logger.info(f"Connecting to MySQL server at {self.host}:{self.port}")
            self._connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                connection_timeout=10,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
            
            # Try to set UTF8MB4 charset and collation
            cursor = self._connection.cursor()
            try:
                logger.debug("Setting UTF8MB4 charset and collation")
                cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
                logger.debug("UTF8MB4 charset set successfully")
            except Error as err:
                if err.errno == 1273:  # Unknown collation
                    logger.warning("UTF8MB4_unicode_ci not supported, falling back to utf8mb4_general_ci")
                    cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_general_ci'")
                else:
                    raise
            cursor.close()
            
            logger.info("Successfully connected to MySQL server")
            return self._connection
            
        except Error as e:
            error_msg = f"Failed to connect to MySQL: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise ReplicationError(error_msg)

    def disconnect(self):
        """Close the MySQL connection"""
        if self._connection and self._connection.is_connected():
            self._connection.close()
            self._connection = None

    def __del__(self):
        """Ensure connection is closed when object is destroyed"""
        self.disconnect()

    def execute_query(self, query, params=None):
        """Execute a query and return results"""
        connection = self.connect()
        cursor = connection.cursor()
        try:
            # Handle multi-line queries by splitting on semicolons
            queries = [q.strip() for q in query.split(';') if q.strip()]
            
            results = []
            for q in queries:
                logger.debug(f"Executing query: {q}")
                if params:
                    cursor.execute(q, params)
                else:
                    cursor.execute(q)
                if cursor.with_rows:  # Only fetch if query produces results
                    results.extend(cursor.fetchall())
            
            logger.debug(f"Raw response: {results}")
            return results
        except Error as e:
            logger.error(f"MySQL Error executing query: {str(e)}", exc_info=True)
            raise ReplicationError(f"Query failed: {str(e)}", query)
        finally:
            cursor.close()

    def check_user_privileges(self, user, host):
        """Check privileges for a specific user"""
        try:
            results = self.execute_query(
                "SHOW GRANTS FOR %s@%s",
                (user, host)
            )
            grants = [grant[0] for grant in results]
            logger.debug(f"Raw grants for {user}@{host}: {grants}")
            
            # Parse privileges from GRANT statements
            privileges = set()
            for grant in grants:
                # Convert to uppercase for consistent comparison
                grant = grant.upper()
                logger.debug(f"Processing grant statement: {grant}")
                
                if 'ALL PRIVILEGES' in grant or ' ALL ' in grant:
                    # User has all privileges
                    logger.debug("Found ALL PRIVILEGES")
                    privileges.update([
                        'REPLICATION SLAVE',
                        'REPLICATION CLIENT',
                        'BINLOG MONITOR',
                        'RELOAD',
                        'SUPER'
                    ])
                    break
                
                # Extract privileges between GRANT and ON using regex
                import re
                if 'GRANT' in grant:
                    # Match everything between GRANT and ON, handling multiple privileges
                    priv_match = re.search(r'GRANT\s+(.*?)\s+ON', grant)
                    if priv_match:
                        priv_part = priv_match.group(1)
                        logger.debug(f"Raw privileges part: {priv_part}")
                        
                        # Split by comma and clean up each privilege
                        grant_privs = re.findall(r'([^,]+?)(?:,|$)', priv_part)
                        grant_privs = [p.strip() for p in grant_privs]
                        logger.debug(f"Split privileges: {grant_privs}")
                        
                        # Map of known privileges and their variations
                        privilege_map = {
                            'REPLICATION SLAVE': ['REPLICATION SLAVE'],
                            'REPLICATION CLIENT': ['REPLICATION CLIENT', 'BINLOG MONITOR'],
                            'BINLOG MONITOR': ['BINLOG MONITOR'],
                            'RELOAD': ['RELOAD'],
                            'SUPER': ['SUPER'],
                            'LOCK TABLES': ['LOCK TABLES']
                        }
                        
                        # Check each privilege against known variations
                        for priv in grant_privs:
                            priv = priv.strip()
                            logger.debug(f"Processing privilege: {priv}")
                            
                            # Check if this privilege matches any known privilege
                            for standard_priv, variations in privilege_map.items():
                                if any(var == priv for var in variations):
                                    privileges.add(standard_priv)
                                    logger.debug(f"Added privilege: {standard_priv}")
                                    break
            
            logger.debug(f"Final parsed privileges for {user}@{host}: {privileges}")
            return list(privileges)
            
        except Error as e:
            logger.error(f"Error checking privileges: {str(e)}", exc_info=True)
            raise ReplicationError(f"Failed to check user privileges: {str(e)}")

    def verify_privileges(self, username, host, required_privileges):
        """Verify that a user has the required privileges"""
        try:
            cursor = self.connect().cursor()
            try:
                # Get all grants for the user
                verify_sql = f"SHOW GRANTS FOR '{username}'@'{host}'"
                logger.info(f"Verifying privileges with: {verify_sql}")
                cursor.execute(verify_sql)
                grants = cursor.fetchall()
                logger.debug(f"Raw SHOW GRANTS output: {grants}")

                # Normalize required privileges
                required_privs = {priv.upper().replace(' ', '_') for priv in required_privileges}
                logger.debug(f"Required privileges (normalized): {required_privs}")
                
                # Parse and check each grant statement
                granted_privs = set()
                for grant in grants:
                    grant_str = grant[0].upper()
                    logger.debug(f"Checking grant: {grant_str}")
                    
                    # If ALL PRIVILEGES is granted, all required privileges are covered
                    if 'ALL PRIVILEGES' in grant_str or ' ALL ' in grant_str:
                        logger.debug("Found ALL PRIVILEGES")
                        granted_privs.update(required_privs)
                        break
                    
                    # Extract privileges from GRANT statement
                    if 'GRANT' in grant_str and 'ON' in grant_str:
                        # Get everything between GRANT and ON
                        priv_part = grant_str[grant_str.find('GRANT') + 5:grant_str.find('ON')].strip()
                        # Split by comma and clean up each privilege
                        grant_privs = [p.strip() for p in priv_part.split(',')]
                        logger.debug(f"Extracted privileges: {grant_privs}")
                        
                        # Check each granted privilege
                        for priv in grant_privs:
                            # Normalize the privilege
                            norm_priv = priv.upper().replace(' ', '_')
                            logger.debug(f"Checking normalized privilege: {norm_priv}")
                            
                            # Handle MariaDB equivalents
                            if norm_priv == 'BINLOG_MONITOR':
                                granted_privs.add('REPLICATION_CLIENT')
                                logger.debug("Found BINLOG_MONITOR, adding REPLICATION_CLIENT")
                            elif norm_priv in required_privs:
                                granted_privs.add(norm_priv)
                                logger.debug(f"Found required privilege: {norm_priv}")
                
                # Check which privileges are missing
                missing_privs = required_privs - granted_privs
                if missing_privs:
                    logger.error(f"Missing privileges: {missing_privs}")
                    logger.error(f"Granted privileges: {granted_privs}")
                    return False, list(missing_privs)
                
                # If all privileges are granted, verify with test queries
                try:
                    if 'REPLICATION_SLAVE' in required_privs:
                        logger.debug("Testing REPLICATION SLAVE privilege...")
                        cursor.execute("SHOW MASTER STATUS")
                        result = cursor.fetchall()
                        logger.debug(f"SHOW MASTER STATUS result: {result}")
                    
                    if 'REPLICATION_CLIENT' in required_privs:
                        logger.debug("Testing REPLICATION CLIENT privilege...")
                        cursor.execute("SHOW SLAVE STATUS")
                        result = cursor.fetchall()
                        logger.debug(f"SHOW SLAVE STATUS result: {result}")
                    
                    logger.info("All test queries executed successfully")
                    return True, []
                    
                except mysql.connector.Error as e:
                    logger.error(f"Test query failed: {str(e)}")
                    return False, [f"Test query failed: {str(e)}"]
                    
            finally:
                cursor.close()
                
        except mysql.connector.Error as e:
            logger.error(f"Error verifying privileges: {str(e)}")
            return False, [str(e)]

    def grant_privileges(self, username, host, privileges):
        """Grant specific privileges to a user"""
        try:
            connection = self.connect()
            cursor = connection.cursor()
            
            try:
                # First check if user exists
                cursor.execute("SELECT 1 FROM mysql.user WHERE user = %s AND host = %s", (username, host))
                result = cursor.fetchall()
                if not cursor.rowcount:
                    logger.error(f"User {username}@{host} does not exist")
                    raise ReplicationError(f"User {username}@{host} does not exist")
                
                # Check if this is MariaDB
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()[0].upper()
                is_mariadb = 'MARIADB' in version
                logger.info(f"Database version: {version}, is_mariadb: {is_mariadb}")
                
                # Convert privileges to list if it's a string
                if isinstance(privileges, str):
                    privileges = [p.strip() for p in privileges.split(',')]
                
                # Map MySQL privileges to MariaDB equivalents
                if is_mariadb:
                    privilege_map = {
                        'REPLICATION CLIENT': 'BINLOG MONITOR',
                        'REPLICATION SLAVE': 'REPLICATION SLAVE'
                    }
                    mapped_privileges = [privilege_map.get(p, p) for p in privileges]
                    logger.info(f"Mapped privileges for MariaDB: {mapped_privileges}")
                else:
                    mapped_privileges = privileges
                
                # Execute GRANT command
                grant_sql = f"GRANT {', '.join(mapped_privileges)} ON *.* TO '{username}'@'{host}'"
                logger.info(f"Executing GRANT command: {grant_sql}")
                try:
                    cursor.execute(grant_sql)
                    cursor.execute("FLUSH PRIVILEGES")
                    logger.info("GRANT command executed successfully")
                except mysql.connector.Error as e:
                    logger.error(f"MySQL error executing GRANT: {str(e)}", exc_info=True)
                    error_msg = str(e)
                    if e.errno == 1045:  # Access denied
                        error_msg = "Access denied. The MySQL user does not have GRANT privilege."
                    elif e.errno == 1044:  # Access denied for GRANT
                        error_msg = "The MySQL user does not have permission to grant privileges."
                    raise ReplicationError(f"MySQL error: {error_msg}")
                
                # Verify the privileges were granted
                success, missing = self.verify_privileges(username, host, mapped_privileges)
                if not success:
                    raise ReplicationError(f"Failed to verify privileges were granted: {', '.join(missing)}")
                
                logger.info("All privileges were successfully granted and verified")
                return True
                
            finally:
                cursor.close()
                
        except mysql.connector.Error as e:
            error_msg = str(e)
            if e.errno == 1045:  # Access denied
                error_msg = "Access denied. The MySQL user does not have GRANT privilege."
            elif e.errno == 1044:  # Access denied for GRANT
                error_msg = "The MySQL user does not have permission to grant privileges."
            logger.error(f"MySQL error in grant_privileges: {error_msg}", exc_info=True)
            raise ReplicationError(f"MySQL error: {error_msg}")

    def create_replication_user(self, repl_user, repl_password, allowed_host, privileges=None):
        """
        Create a replication user with specified privileges.
        If privileges is None, it will default to the legacy "REPLICATION SLAVE".
        For the source (master), call with privileges="REPLICATION SLAVE, REPLICATION CLIENT"
        and for the target (slave), call with privileges="REPLICATION CLIENT".
        """
        try:
            connection = self.connect()
            cursor = connection.cursor()
            
            # Check if this is MariaDB
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0].upper()
            is_mariadb = 'MARIADB' in version
            logger.info(f"Database version: {version}, is_mariadb: {is_mariadb}")
            
            create_user_sql = f"CREATE USER '{repl_user}'@'{allowed_host}' IDENTIFIED BY '{repl_password}'"
            
            # If no privileges provided, fall back to legacy behavior.
            if privileges is None:
                privileges = "REPLICATION SLAVE"
            
            # Map MySQL privileges to MariaDB equivalents
            if is_mariadb:
                privileges = privileges.replace('REPLICATION CLIENT', 'BINLOG MONITOR')
            
            grant_sql = f"GRANT {privileges} ON *.* TO '{repl_user}'@'{allowed_host}'"
            
            try:
                cursor.execute(create_user_sql)
                cursor.execute(grant_sql)
                cursor.execute("FLUSH PRIVILEGES")
                return True
            except Error as e:
                # If the user already exists, drop and recreate the user.
                if e.errno == 1396:
                    cursor.execute(f"DROP USER '{repl_user}'@'{allowed_host}'")
                    cursor.execute(create_user_sql)
                    cursor.execute(grant_sql)
                    cursor.execute("FLUSH PRIVILEGES")
                    return True
                raise
            finally:
                cursor.close()
        except Error as e:
            raise ReplicationError(f"Failed to create replication user: {str(e)}")

    def get_master_status(self):
        """Get master status information"""
        try:
            results = self.execute_query("SHOW MASTER STATUS")
            if not results:
                raise ReplicationError("No master status information available")
            
            # Results format: (File, Position, Binlog_Do_DB, Binlog_Ignore_DB, Executed_Gtid_Set)
            return {
                'file': results[0][0],
                'position': results[0][1],
                'binlog_do_db': results[0][2],
                'binlog_ignore_db': results[0][3],
                'executed_gtid_set': results[0][4] if len(results[0]) > 4 else None
            }
        except Error as e:
            raise ReplicationError(f"Failed to get master status: {str(e)}")

    def setup_slave(self, master_host, master_port, repl_user, repl_password, master_log_file, master_log_pos, databases=None):
        """Configure slave for replication"""
        print("Setting up slave...")
        try:
            connection = self.connect()
            cursor = connection.cursor()
            
            try:
                # Stop slave if it's running
                cursor.execute("STOP SLAVE")
                
                # Configure slave
                change_master_sql = f"""
                CHANGE MASTER TO
                    MASTER_HOST = '{master_host}',
                    MASTER_PORT = {master_port},
                    MASTER_USER = '{repl_user}',
                    MASTER_PASSWORD = '{repl_password}',
                    MASTER_LOG_FILE = '{master_log_file}',
                    MASTER_LOG_POS = {master_log_pos}
                """
                cursor.execute(change_master_sql)

                is_mariadb = 'mariadb' in self.execute_query("SELECT VERSION()")[0][0].lower()
                if is_mariadb:
                    cursor.execute("SET GLOBAL replicate_do_db = ''")
                else:
                    cursor.execute("CHANGE REPLICATION FILTER REPLICATE_DO_DB = ()")

                if databases:
                    db_list_str = ','.join(databases)
                    if is_mariadb:
                        filter_sql = f"SET GLOBAL replicate_do_db = '{db_list_str}'"
                    else:
                        filter_sql = f"CHANGE REPLICATION FILTER REPLICATE_DO_DB = ({','.join(f'`{db}`' for db in databases)})"
                    cursor.execute(filter_sql)

                # Start slave
                cursor.execute("START SLAVE")
                
                return True
            finally:
                cursor.close()
                
        except Error as e:
            raise ReplicationError(f"Failed to setup slave: {str(e)}")

    def check_slave_status(self):
        """Get slave status information"""
        try:
            connection = self.connect()
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute("SHOW SLAVE STATUS")
                result = cursor.fetchone()
                if not result:
                    return None
                
                # Ensure Replicate_Do_DB is an empty string if it's None or N/A
                if result.get('Replicate_Do_DB') is None or result.get('Replicate_Do_DB') == 'N/A':
                    result['Replicate_Do_DB'] = ''

                # Check for errors and add to the result if found
                if result.get('Last_Error'):
                    result['error'] = result['Last_Error']
                    
                return result
            finally:
                cursor.close()
        except Exception as e:
            import traceback
            logger.error(f"Exception in check_slave_status: {e}", exc_info=True)
            return {
                'error': f'Failed to check slave status: {str(e)}',
                'traceback': traceback.format_exc()
            }

    def get_server_variables(self):
        """Get important server variables for replication"""
        try:
            variables = {}
            query = """
            SHOW VARIABLES WHERE Variable_name IN (
                'server_id',
                'log_bin',
                'binlog_format',
                'binlog_row_image',
                'gtid_mode',
                'enforce_gtid_consistency'
            )
            """
            results = self.execute_query(query)
            for var_name, var_value in results:
                variables[var_name] = var_value
            return variables
            
        except Error as e:
            raise ReplicationError(f"Failed to get server variables: {str(e)}")

    def clean_slave(self):
        """Stop and reset a slave"""
        try:
            connection = self.connect()
            cursor = connection.cursor()
            try:
                logger.info("Executing STOP SLAVE")
                cursor.execute("STOP SLAVE")
                logger.info("Executing RESET SLAVE ALL")
                cursor.execute("RESET SLAVE ALL")
                return True, "Slave cleaned successfully."
            finally:
                cursor.close()
        except Error as e:
            logger.error(f"Failed to clean slave: {str(e)}", exc_info=True)
            raise ReplicationError(f"Failed to clean slave: {str(e)}")
