# iLearn Backend - Learning App API

A comprehensive Flask-based REST API backend for an Android learning application with authentication, course management, and admin functionalities.

## Features

### Authentication System
- ✅ Student registration and login
- ✅ JWT-based authentication
- ✅ Role-based access control (Admin/Student)
- ✅ Secure password hashing with Bcrypt
- ✅ Profile photo upload for authenticated users

### Course Management
- ✅ Create, Read, Update, Delete (CRUD) operations
- ✅ Course enrollment system
- ✅ Course content and resource upload
- ✅ Enrolled student progress tracking
- ✅ Reviews and ratings
- ✅ Testimonials
- ✅ Search and filter courses
- ✅ Admin-only course creation/modification

### Admin Features
- ✅ Dashboard statistics
- ✅ User management
- ✅ Course management
- ✅ Admin privileges verification

## Tech Stack

- **Framework**: Flask 3.0
- **Database**: MongoDB
- **Authentication**: JWT (JSON Web Tokens)
- **Password Hashing**: Bcrypt
- **CORS**: Flask-CORS

## Web Interface

The project includes ready-to-use HTML pages:

### 🎯 Admin Dashboard (`admin.html`)
- Admin login and registration
- Real-time dashboard statistics
- Course creation with full details
- Dynamic form fields for teachers, syllabus, prerequisites
- Modern, responsive UI

### 📚 Student Course Catalog (`index.html`)
- Browse all available courses
- Search and filter by category/level
- View detailed course information
- See ratings and reviews
- Responsive course cards

**To use:** Open the HTML files directly in your browser after starting the Flask server.

## Installation

### Prerequisites
- Python 3.8 or higher
- MongoDB installed and running locally or a MongoDB Atlas account
- pip (Python package manager)

### Setup Steps

1. **Clone the repository**
   ```bash
   cd "iLearn Backend"
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**
   - Windows:
     ```bash
     venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables**
   ```bash
   copy .env.example .env
   ```
   
   Edit `.env` file and update the values:
   ```
   MONGO_URI=mongodb://localhost:27017/ilearn_db
   JWT_SECRET_KEY=your-super-secret-jwt-key
   SECRET_KEY=your-super-secret-key
   ```

6. **Start MongoDB**
   - If using local MongoDB:
     ```bash
     mongod
     ```
   - If using MongoDB Atlas, update MONGO_URI in .env with your connection string

7. **Run the application**
   ```bash
   python main.py
   ```

The API will be available at `http://localhost:5000`

## Bulk Upload Same Content to All Courses

Use the prepared files in `bulk_upload/` to upload the same content and resource to every course.

### Files
- `bulk_upload/bulk_upload_config.json` - configuration (base URL, admin token, file paths)
- `bulk_upload/shared-content.txt` - sample content file
- `bulk_upload/shared-resource.txt` - sample resource file
- `bulk_upload/upload_same_content_all_courses.ps1` - automation script

### Run (Windows PowerShell)
1. Update `bulk_upload/bulk_upload_config.json`:
  - Set `admin_token`
  - Optionally change titles/file paths
2. Run:
  ```powershell
  powershell -ExecutionPolicy Bypass -File bulk_upload/upload_same_content_all_courses.ps1
  ```

The script fetches courses using `/api/courses`, uploads content to each course via `/api/courses/<course_id>/content/upload`, and uploads resources via `/api/courses/<course_id>/resources/upload`.

## API Endpoints

### Authentication

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "securepassword",
  "phone": "+1234567890",
  "role": "student"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "john@example.com",
  "password": "securepassword"
}
```

#### Get Profile
```http
GET /api/auth/profile
Authorization: Bearer <access_token>
```

#### Upload Profile Photo
```http
POST /api/auth/profile/photo
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <image_file>
```

Supported formats: JPG, JPEG, PNG, GIF, WebP (max 5MB)

### Courses

#### Create Course (Admin Only)
```http
POST /api/courses
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "name": "Python Programming for Beginners",
  "description": "Learn Python from scratch",
  "price": 2999,
  "duration": "8 weeks",
  "level": "Beginner",
  "category": "Programming",
  "batch": "Batch-2024-01",
  "teachers": [
    {
      "name": "Dr. Smith",
      "qualification": "PhD in Computer Science",
      "experience": "10 years"
    }
  ],
  "syllabus": [
    "Introduction to Python",
    "Variables and Data Types",
    "Control Flow",
    "Functions and Modules"
  ],
  "prerequisites": ["Basic computer knowledge"],
  "learning_outcomes": [
    "Write Python programs",
    "Understand OOP concepts"
  ],
  "thumbnail": "https://example.com/thumbnail.jpg",
  "video_url": "https://example.com/intro-video.mp4"
}
```

#### Get All Courses
```http
GET /api/courses
GET /api/courses?category=Programming
GET /api/courses?level=Beginner
GET /api/courses?search=python
```

#### Get Course by ID
```http
GET /api/courses/<course_id>
```

#### Update Course (Admin Only)
```http
PUT /api/courses/<course_id>
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "name": "Updated Course Name",
  "price": 3499
}
```

#### Delete Course (Admin Only)
```http
DELETE /api/courses/<course_id>
Authorization: Bearer <admin_access_token>
```

#### Enroll in Course
```http
POST /api/courses/<course_id>/enroll
Authorization: Bearer <access_token>
```

#### Upload Course Content (Admin Only)
```http
POST /api/courses/<course_id>/content/upload
Authorization: Bearer <admin_access_token>
Content-Type: multipart/form-data

file: <content_file>
title: <content_title>
description: <optional_description>
content_type: <optional_type>
```

#### Upload Course Resource (Admin Only)
```http
POST /api/courses/<course_id>/resources/upload
Authorization: Bearer <admin_access_token>
Content-Type: multipart/form-data

file: <resource_file>
title: <optional_title>
content_id: <optional_content_id>
```

#### Get Enrolled Course Content (Enrolled Student)
```http
GET /api/courses/<course_id>/content
Authorization: Bearer <access_token>
```

#### Update Course Progress (Enrolled Student)
```http
POST /api/courses/<course_id>/progress
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "content_id": "<content_id>",
  "completed": true,
  "current_position_seconds": 120
}
```

#### Get Course Progress (Enrolled Student)
```http
GET /api/courses/<course_id>/progress
Authorization: Bearer <access_token>
```

#### Add Review and Rating
```http
POST /api/courses/<course_id>/review
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "rating": 5,
  "comment": "Excellent course! Very well structured."
}
```

### Admin

#### Get Dashboard Statistics (Admin Only)
```http
GET /api/admin/stats
Authorization: Bearer <admin_access_token>
```

#### Get All Users (Admin Only)
```http
GET /api/admin/users
Authorization: Bearer <admin_access_token>
```

### Health Check

#### Health Check
```http
GET /api/health
```

#### Root Endpoint
```http
GET /
```

## Course Data Model

```json
{
  "_id": "ObjectId",
  "name": "Course Name",
  "description": "Course Description",
  "price": 2999,
  "duration": "8 weeks",
  "level": "Beginner|Intermediate|Advanced",
  "category": "Category Name",
  "batch": "Batch Identifier",
  "teachers": [
    {
      "name": "Teacher Name",
      "qualification": "Qualification",
      "experience": "Experience"
    }
  ],
  "syllabus": ["Topic 1", "Topic 2"],
  "prerequisites": ["Prerequisite 1"],
  "learning_outcomes": ["Outcome 1"],
  "thumbnail": "image_url",
  "video_url": "video_url",
  "status": "active|inactive",
  "enrolled_students": 0,
  "reviews": [
    {
      "user_id": "user_id",
      "user_name": "User Name",
      "rating": 5,
      "comment": "Review comment",
      "created_at": "timestamp"
    }
  ],
  "ratings": {
    "average": 4.5,
    "count": 10,
    "distribution": {
      "1": 0,
      "2": 1,
      "3": 2,
      "4": 3,
      "5": 4
    }
  },
  "testimonials": [],
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

## User Data Model

```json
{
  "_id": "ObjectId",
  "name": "User Name",
  "email": "user@example.com",
  "password": "hashed_password",
  "role": "student|admin",
  "phone": "+1234567890",
  "enrolled_courses": ["course_id_1", "course_id_2"],
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

## Creating an Admin User

To create an admin user, register a user with `"role": "admin"`:

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Admin User",
    "email": "admin@ilearn.com",
    "password": "admin123",
    "role": "admin"
  }'
```

## Testing with cURL

### Register a Student
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"John Doe\",\"email\":\"john@example.com\",\"password\":\"password123\"}"
```

### Login
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"john@example.com\",\"password\":\"password123\"}"
```

### Create a Course (as Admin)
```bash
curl -X POST http://localhost:5000/api/courses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d "{\"name\":\"Python Course\",\"description\":\"Learn Python\",\"price\":2999}"
```

### Get All Courses
```bash
curl http://localhost:5000/api/courses
```

## Error Handling

The API returns appropriate HTTP status codes:

- `200 OK` - Successful request
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Authentication required or failed
- `403 Forbidden` - Insufficient privileges
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

Error Response Format:
```json
{
  "error": "Error message description"
}
```

## Security Best Practices

1. **Change default secrets**: Update `JWT_SECRET_KEY` and `SECRET_KEY` in production
2. **Use HTTPS**: Always use HTTPS in production
3. **MongoDB Security**: Enable authentication and use strong passwords
4. **Environment Variables**: Never commit `.env` file to version control
5. **Rate Limiting**: Consider adding rate limiting for production
6. **Input Validation**: The API validates all inputs, but additional validation can be added

## Database Indexes (Recommended)

For better performance, create these indexes in MongoDB:

```javascript
// Users collection
db.users.createIndex({ "email": 1 }, { unique: true })
db.users.createIndex({ "role": 1 })

// Courses collection
db.courses.createIndex({ "status": 1 })
db.courses.createIndex({ "category": 1 })
db.courses.createIndex({ "level": 1 })
db.courses.createIndex({ "name": "text", "description": "text" })
```

## Future Enhancements

- [ ] Password reset functionality
- [ ] Email verification
- [ ] Payment integration
- [ ] File upload for course materials
- [ ] Video streaming
- [ ] Progress tracking
- [ ] Certificates generation
- [ ] Push notifications
- [ ] Social authentication (Google, Facebook)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License.

## Support

For issues and questions, please create an issue in the repository or contact the development team.

---

**Happy Learning! 🚀**
