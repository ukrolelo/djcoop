# Djcoop - IT Management Suite

![Djcoop Project](static/img/djcoop_gh_1_tr.png)

A comprehensive Django project consisting of multiple applications designed to help with IT work and document management.

## Applications Overview

### 1. DjSQL - MariaDB SQL Replication Management
The original application focuses on setting up and managing MariaDB SQL replication between servers.

### 2. DjMail - Email Management System (Under Development)
Email account management and processing system for handling multiple email accounts.

### 3. DjNote - Document & Note Scanner
A mobile-friendly document scanning and management application with the following features:

#### Core Features
- **Document Scanning**: Take photos or upload images from gallery
- **Multi-page Support**: One scan can contain multiple pages
- **Document vs Note Classification**: Choose between document or note when saving
- **Automatic Document ID**: Documents get unique sequential IDs (e.g., 000001, 000002)
- **Retention Management**: Set how long documents should be stored
- **Due Date Tracking**: Automatic calculation of deletion due dates
- **Archive System**: Archive documents instead of permanent deletion
- **Search & Filter**: Search by title, description, or document ID
- **Mobile Optimized**: Responsive design for mobile document scanning

#### Technical Features
- **Thumbnail Generation**: Automatic thumbnail creation for fast loading
- **Image Optimization**: Efficient storage and display of scanned images
- **User Isolation**: Each user sees only their own scans

### 4. Import/Export System
The project includes a comprehensive backup and restore system:

#### Features
- **Database Backup**: Export all application data in JSON format
- **Media File Backup**: Include uploaded files (scans, attachments) in backups
- **Selective Export**: Choose which applications to include in backup
- **Progress Tracking**: Real-time progress monitoring for large operations
- **User Data Protection**: Includes user accounts and permissions in backups

#### Supported Data
- **DjSQL**: Database servers and user configurations
- **DjMail**: Email accounts, folders, messages, and attachments
- **DjNote**: Scanned documents, pages, and associated media files
- **User Management**: User accounts, groups, and permissions

## Installation and Setup

### Prerequisites
- Python 3.8+
- Django 4.2+
- Pillow (for image processing in DjNote)
- Other dependencies listed in `requirements.txt`

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd djcoop
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Apply database migrations:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. **Create superuser (optional):**
   ```bash
   python manage.py createsuperuser
   ```

5. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

### Application URLs
- **Main Dashboard**: `/` - Central hub with links to all applications
- **DjSQL**: `/djsql/` - MariaDB replication management
- **DjMail**: `/mail/` - Email management system
- **DjNote**: `/notes/` - Document and note scanner
- **Admin Panel**: `/admin/` - Django administration interface


## MariaDB SQL Replication Setup (DjSQL)

The DjSQL application provides a web interface for managing MariaDB replication between servers. This was the original component of the djcoop project.

### Key Features
- Server configuration management
- Replication status monitoring
- User and database management
- Connection testing and validation

**The original MariaDB replication component was built with the assistance of [`refact.ai "KUDOS Refact Team"`](https://refact.ai/).**

## Screenshots

### DjSQL - MariaDB Replication Management
![Screenshot 1](static/img/screenshots/screen1.png)
![Screenshot 2](static/img/screenshots/screen2.png)
![Screenshot 3](static/img/screenshots/screen3.png)
![Screenshot 4](static/img/screenshots/screen4.png)
![Screenshot 5](static/img/screenshots/screen5.png)
![Screenshot 6](static/img/screenshots/screen6.png)
![Screenshot 7](static/img/screenshots/screen7.png)
![Screenshot 8](static/img/screenshots/screen8.png)


### Example Testing with Demo Servers (Docker Compose)

The `docker-examples` folder contains configurations for two MariaDB servers (`dbserver1` and `dbserver2`) designed to demonstrate replication.

#### Server 1: `dbserver1`

Navigate to `docker-examples/dbserver1/` and run `docker compose up -d`.

**`docker-examples/dbserver1/docker-compose-dbserver1.yaml`:**
```yaml
version: "3.8"
services:
  mariadb1:
    image: mariadb:latest
    container_name: mariadb1
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: your_root_password1
      MYSQL_DATABASE: your_database1
      MYSQL_USER: your_user1
      MYSQL_PASSWORD: your_password1
    ports:
      - 9991:3306
    volumes:
      - /mnt/docksync_ns/mysql1/custom/my-custom.cnf:/etc/mysql/conf.d/my-custom.cnf
      - /mnt/docksync_ns/mysql1/data:/var/lib/mysql
      - /mnt/docksync_ns/mysql1/init:/docker-entrypoint-initdb.d
    command: --bind-address=0.0.0.0
networks: {}
```
*   **`image: mariadb:latest`**: Specifies the MariaDB Docker image to use.
*   **`container_name: mariadb1`**: Assigns a recognizable name to the container.
*   **`ports: - 9991:3306`**: Maps port 9991 on your host to port 3306 inside the container, allowing access to MariaDB.
*   **`volumes`**: Mounts local directories into the container for custom configurations, persistent data, and initialization scripts.
    *   The `/docker-entrypoint-initdb.d` volume is used to place initialization scripts. The `remote_access.sql` file, located at `docker-examples/dbserver1/mysql1/init/remote_access.sql`, is used to grant remote access privileges to the database user:
        ```sql
        GRANT ALL PRIVILEGES ON *.* TO 'your_user1'@'%' IDENTIFIED BY 'your_password1' WITH GRANT OPTION;
        FLUSH PRIVILEGES;
        ```

#### Server 2: `dbserver2`

Navigate to `docker-examples/dbserver2/` and run `docker compose up -d`.

**`docker-examples/dbserver2/docker-compose-dbserver2.yaml`:**
```yaml
version: "3.8"
services:
  mariadb2:
    image: mariadb:latest
    container_name: mariadb2
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: your_root_password2
      MYSQL_DATABASE: your_database2
      MYSQL_USER: your_user2
      MYSQL_PASSWORD: your_password2
    ports:
      - 9992:3306
    volumes:
      - /mnt/docksync_ns/mysql2/custom/my-custom.cnf:/etc/mysql/conf.d/my-custom.cnf
      - /mnt/docksync_ns/mysql2/data:/var/lib/mysql
      - /mnt/docksync_ns/mysql2/init:/docker-entrypoint-initdb.d
    command: --bind-address=0.0.0.0
networks: {}
```
*   Similar to `dbserver1`, but uses `mariadb2` as container name and maps to host port `9992`.
*   The `init` volume also contains a `remote_access.sql` file for granting remote access.

#### Custom MariaDB Configuration (`my-custom.cnf`)

This file is mounted into the MariaDB containers to configure replication and other settings.

**`docker-examples/dbserver1/mysql1/custom/my-custom.cnf`:**
```ini
[mysqld]
log_bin = mysql-bin
server-id = 1
binlog_format = ROW
character-set-server = utf8mb4
collation-server = utf8mb4_general_ci
```
*   **`log_bin = mysql-bin`**: Enables binary logging, which is essential for replication.
*   **`server-id = 1` (for `dbserver1`)**: Each server in a replication topology must have a unique `server-id`. `dbserver1` uses `1`, and `dbserver2` (not shown here, but configured similarly in its `my-custom.cnf`) uses `10` to ensure distinct identification within the replication setup.
*   **`binlog_format = ROW`**: Specifies the format for binary logging, `ROW` is generally recommended for safety and consistency in replication.
*   **`character-set-server = utf8mb4`** and **`collation-server = utf8mb4_general_ci`**: Set the default character set and collation for the server.

## Features Summary

### Current Capabilities
- ✅ **MariaDB Replication Management** - Complete setup and monitoring
- ✅ **Email Account Management** - Multi-account email processing
- ✅ **Document Scanning** - Mobile-friendly document capture and management
- ✅ **Data Import/Export** - Full project backup and restore capabilities
- ✅ **User Management** - Multi-user support with data isolation
- ✅ **Responsive Design** - Works on desktop and mobile devices

### Technical Highlights
- **Django 4.2+** framework with modern best practices
- **Bootstrap CSS** for consistent, responsive UI
- **Image Processing** with Pillow for document thumbnails
- **Database Agnostic** - Works with SQLite, PostgreSQL, MySQL/MariaDB
- **Modular Architecture** - Each app can be used independently
- **Comprehensive Logging** - Detailed logs for troubleshooting



## License

This project is developed for personal use. Please respect any third-party licenses for included dependencies.

---

**Development Tools Used:**
- Original MariaDB component: [`refact.ai`](https://refact.ai/)
- Additional development: Various AI coding assistants and manual development
