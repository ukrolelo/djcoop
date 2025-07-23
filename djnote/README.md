# DjNote - Document & Note Scanner

A Django app for scanning and managing documents and notes with mobile-friendly features.

## Features

### Core Functionality
- **Document Scanning**: Take photos or upload images from gallery
- **Multi-page Support**: One scan can contain multiple pages
- **Document vs Note Classification**: Choose between document or note when saving
- **Automatic Document ID**: Documents get unique sequential IDs (e.g., 000001, 000002)
- **Retention Management**: Set how long documents should be stored
- **Due Date Tracking**: Automatic calculation of deletion due dates

### Mobile-Optimized
- **Camera Integration**: Direct camera access on mobile devices
- **Touch-Friendly Interface**: Optimized for mobile interaction
- **Responsive Design**: Works on phones, tablets, and desktop

### Document Management
- **Due Documents List**: View documents that need deletion (sorted by due date)
- **Status Indicators**: Visual alerts for overdue and due-soon documents
- **Search & Filter**: Find documents by title, description, or ID
- **Archive System**: Archive documents without deleting them

### Technical Features
- **Thumbnail Generation**: Automatic thumbnail creation for fast loading
- **Image Optimization**: Efficient storage and display of scanned images
- **User Isolation**: Each user sees only their own scans
- **Date Format**: Uses DD.MM.YYYY HH:MM format as requested

## Usage

### Creating a New Scan
1. Click "New Scan" button
2. Enter title and description
3. Choose type: Document or Note
4. For documents: Set retention period in days
5. Upload one or more images
6. Save the scan

### Managing Documents
- View all scans in the main dashboard
- Use "Due Documents" to see items needing attention
- Edit scan details or add more pages anytime
- Archive or delete scans as needed

### Mobile Scanning
- On mobile devices, the file input will offer camera option
- Take multiple photos in sequence
- Images are automatically numbered as pages

## Management Commands

### Cleanup Due Documents
```bash
# List documents due for deletion
python manage.py cleanup_due_documents

# Include documents due within 7 days
python manage.py cleanup_due_documents --days 7

# Actually delete overdue documents
python manage.py cleanup_due_documents --delete
```

## Models

### Scan
- Main container for documents/notes
- Tracks type, retention period, due dates
- Auto-generates document IDs for documents

### ScanPage
- Individual pages within a scan
- Stores original image and thumbnail
- Maintains page order

## URL Structure
- `/notes/` - Main dashboard
- `/notes/create/` - Create new scan
- `/notes/due/` - Due documents list
- `/notes/scan/<id>/` - View scan details
- `/notes/scan/<id>/edit/` - Edit scan
- `/notes/scan/<id>/add-pages/` - Add more pages

## Installation Notes
- Requires Pillow for image processing
- Uses Django's built-in ImageField for file storage
- Media files stored in `media/scans/` directory
- Thumbnails stored in `media/scans/thumbnails/`
