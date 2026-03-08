from flask import Flask, request, jsonify, send_file
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from functools import wraps
import os
import base64
import io
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
app.config['MONGO_URI'] = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/ilearn_db')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-this')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

# Initialize extensions
mongo = PyMongo(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
CORS(app)

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
IMAGE_FOLDER = os.path.join(UPLOAD_FOLDER, 'images')
VIDEO_FOLDER = os.path.join(UPLOAD_FOLDER, 'videos')
RESOURCE_FOLDER = os.path.join(UPLOAD_FOLDER, 'resources')

# Create upload folders if they don't exist (use /tmp on read-only filesystems)
try:
    os.makedirs(IMAGE_FOLDER, exist_ok=True)
    os.makedirs(VIDEO_FOLDER, exist_ok=True)
    os.makedirs(RESOURCE_FOLDER, exist_ok=True)
except OSError as e:
    if e.errno == 30:  # Read-only file system
        UPLOAD_FOLDER = '/tmp/uploads'
        IMAGE_FOLDER = os.path.join(UPLOAD_FOLDER, 'images')
        VIDEO_FOLDER = os.path.join(UPLOAD_FOLDER, 'videos')
        RESOURCE_FOLDER = os.path.join(UPLOAD_FOLDER, 'resources')
        os.makedirs(IMAGE_FOLDER, exist_ok=True)
        os.makedirs(VIDEO_FOLDER, exist_ok=True)
        os.makedirs(RESOURCE_FOLDER, exist_ok=True)
    else:
        raise

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Database collections (lazy initialization to handle connection delays)
class LazyCollection:
    def __init__(self, collection_name):
        self.collection_name = collection_name
        self._collection = None
    
    def _get_collection(self):
        if self._collection is None:
            if mongo.db is None:
                raise RuntimeError(f"MongoDB not connected yet")
            self._collection = getattr(mongo.db, self.collection_name)
        return self._collection
    
    def __getattr__(self, name):
        return getattr(self._get_collection(), name)

users_collection = LazyCollection('users')
courses_collection = LazyCollection('courses')
payments_collection = LazyCollection('payments')

# Helper function to serialize MongoDB documents
def serialize_doc(doc):
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

# Admin required decorator
def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        if not user or user.get('role') != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403
        return fn(*args, **kwargs)
    return wrapper

def is_user_enrolled(user, course_id):
    return course_id in user.get('enrolled_courses', [])

def format_progress_response(progress_data, total_contents):
    response = {
        'course_id': progress_data.get('course_id', ''),
        'completed_content_ids': progress_data.get('completed_content_ids', []),
        'last_content_id': progress_data.get('last_content_id', ''),
        'current_position_seconds': progress_data.get('current_position_seconds', 0),
        'progress_percent': progress_data.get('progress_percent', 0),
        'total_contents': total_contents,
        'completed_count': len(progress_data.get('completed_content_ids', []))
    }

    started_at = progress_data.get('started_at')
    updated_at = progress_data.get('updated_at')
    response['started_at'] = started_at.isoformat() if isinstance(started_at, datetime) else started_at
    response['updated_at'] = updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at

    return response

# ==================== Authentication Routes ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new student"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('email') or not data.get('password') or not data.get('name'):
            return jsonify({'error': 'Email, password, and name are required'}), 400
        
        # Check if user already exists
        if users_collection.find_one({'email': data['email']}):
            return jsonify({'error': 'Email already registered'}), 400
        
        # Hash password
        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
        # Create user document
        user = {
            'name': data['name'],
            'email': data['email'],
            'password': hashed_password,
            'role': data.get('role', 'student'),  # Default role is student
            'phone': data.get('phone', ''),
            'profile_photo': '',
            'enrolled_courses': [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert user
        result = users_collection.insert_one(user)
        user_id = str(result.inserted_id)
        
        # Create access token
        access_token = create_access_token(identity=user_id)
        
        return jsonify({
            'message': 'User registered successfully',
            'user': {
                'id': user_id,
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'profile_photo': user.get('profile_photo', ''),
                'enrolled_courses': user['enrolled_courses']
            },
            'access_token': access_token
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user
        user = users_collection.find_one({'email': data['email']})
        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Verify password
        if not bcrypt.check_password_hash(user['password'], data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Create access token
        access_token = create_access_token(identity=str(user['_id']))
        
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': str(user['_id']),
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'profile_photo': user.get('profile_photo', ''),
                'enrolled_courses': user.get('enrolled_courses', [])
            },
            'access_token': access_token
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile"""
    try:
        current_user_id = get_jwt_identity()
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user_data = serialize_doc(user)
        user_data.pop('password', None)  # Remove password from response
        
        return jsonify({'user': user_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/profile/photo', methods=['POST'])
@jwt_required()
def upload_profile_photo():
    """Upload and update user's profile photo"""
    try:
        current_user_id = get_jwt_identity()
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})

        if not user:
            return jsonify({'error': 'User not found'}), 404

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Only image files allowed (JPG, PNG, GIF, WebP)'}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'Image size exceeds 5MB limit'}), 400

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"profile_{current_user_id}_{timestamp}_{secure_filename(file.filename)}"
        filepath = os.path.join(IMAGE_FOLDER, unique_filename)

        file.save(filepath)

        old_photo = user.get('profile_photo', '')
        if old_photo.startswith('/api/files/images/'):
            old_filename = secure_filename(old_photo.split('/')[-1])
            old_filepath = os.path.join(IMAGE_FOLDER, old_filename)
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except OSError:
                    pass

        profile_photo_url = f"{request.host_url}/api/files/images/{unique_filename}"

        users_collection.update_one(
            {'_id': ObjectId(current_user_id)},
            {
                '$set': {
                    'profile_photo': profile_photo_url,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        return jsonify({
            'message': 'Profile photo uploaded successfully',
            'profile_photo': profile_photo_url,
            'filename': unique_filename,
            'size': file_size
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Course Routes ====================

@app.route('/api/courses', methods=['POST'])
@admin_required
def create_course():
    """Create a new course (Admin only)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('description'):
            return jsonify({'error': 'Name and description are required'}), 400
        
        # Create course document
        course = {
            'name': data['name'],
            'description': data['description'],
            'price': data.get('price', 0),
            'duration': data.get('duration', ''),
            'level': data.get('level', 'Beginner'),
            'category': data.get('category', ''),
            'batch': data.get('batch', ''),
            'teachers': data.get('teachers', []),
            'syllabus': data.get('syllabus', []),
            'prerequisites': data.get('prerequisites', []),
            'learning_outcomes': data.get('learning_outcomes', []),
            'thumbnail': data.get('thumbnail', ''),
            'video_url': data.get('video_url', ''),
            'status': data.get('status', 'active'),
            'enrolled_students': 0,
            'contents': [],
            'course_resources': [],
            'reviews': [],
            'ratings': {
                'average': 0,
                'count': 0,
                'distribution': {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0}
            },
            'testimonials': [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert course
        result = courses_collection.insert_one(course)
        course_id = str(result.inserted_id)
        
        return jsonify({
            'message': 'Course created successfully',
            'course_id': course_id,
            'course': serialize_doc(course)
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses', methods=['GET'])
def get_courses():
    """Get all courses with optional filters"""
    try:
        # Get query parameters for filtering
        category = request.args.get('category')
        level = request.args.get('level')
        status = request.args.get('status', 'active')
        search = request.args.get('search')
        
        # Build query
        query = {'status': status}
        if category:
            query['category'] = category
        if level:
            query['level'] = level
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'description': {'$regex': search, '$options': 'i'}}
            ]
        
        # Get courses
        courses = list(courses_collection.find(query).sort('created_at', -1))
        # Serialize courses
        for course in courses:
            serialize_doc(course)
        
        return jsonify({
            'count': len(courses),
            'courses': courses
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>', methods=['GET'])
def get_course(course_id):
    """Get a specific course by ID"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400
        
        # Find course
        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404
        
        return jsonify({'course': serialize_doc(course)}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>', methods=['PUT'])
@admin_required
def update_course(course_id):
    """Update a course (Admin only)"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400
        
        data = request.get_json()
        
        # Remove fields that shouldn't be updated directly
        data.pop('_id', None)
        data.pop('reviews', None)
        data.pop('ratings', None)
        data.pop('enrolled_students', None)
        data.pop('created_at', None)
        
        # Update timestamp
        data['updated_at'] = datetime.utcnow()
        
        # Update course
        result = courses_collection.update_one(
            {'_id': ObjectId(course_id)},
            {'$set': data}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Course not found'}), 404
        
        # Get updated course
        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        
        return jsonify({
            'message': 'Course updated successfully',
            'course': serialize_doc(course)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>', methods=['DELETE'])
@admin_required
def delete_course(course_id):
    """Delete a course (Admin only)"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400
        
        # Delete course
        result = courses_collection.delete_one({'_id': ObjectId(course_id)})
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Course not found'}), 404
        
        return jsonify({'message': 'Course deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/enroll', methods=['POST'])
@jwt_required()
def enroll_course(course_id):
    """Enroll in a course"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400
        
        current_user_id = get_jwt_identity()
        
        # Check if course exists
        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404
        
        # Check if already enrolled
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        if is_user_enrolled(user, course_id):
            return jsonify({'error': 'Already enrolled in this course'}), 400
        
        # Add course to user's enrolled courses
        users_collection.update_one(
            {'_id': ObjectId(current_user_id)},
            {'$push': {'enrolled_courses': course_id}}
        )
        
        # Increment enrolled students count
        courses_collection.update_one(
            {'_id': ObjectId(course_id)},
            {'$inc': {'enrolled_students': 1}}
        )
        
        return jsonify({'message': 'Successfully enrolled in course'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/enroll-with-payment', methods=['POST'])
@jwt_required()
def enroll_with_payment(course_id):
    """Enroll in a course with payment information"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400
        
        data = request.get_json()
        current_user_id = data.get("user_id", get_jwt_identity())  # Use user_id from token if not provided in body
        
        # Validate required payment fields
        required_fields = ['amount', 'payment_method']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate payment amount
        try:
            amount = float(data['amount'])
            if amount <= 0:
                return jsonify({'error': 'Payment amount must be greater than 0'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid payment amount'}), 400
        
        # Check if course exists
        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404
        
        # Get user details
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if already enrolled
        if is_user_enrolled(user, course_id):
            return jsonify({'error': 'Already enrolled in this course'}), 400
        
        # Verify payment amount matches course price (optional validation)
        if course.get('price', 0) > 0 and amount < course.get('price', 0):
            return jsonify({'error': 'Payment amount is less than course price'}), 400
        
        print(current_user_id, course_id, amount, data.get("transaction_id"))  # Debugging log
        # Create payment record
        payment = {
            'user_id': current_user_id,
            'user_name': user['name'],
            'user_email': user['email'],
            'course_id': course_id,
            'course_name': course['name'],
            'amount': amount,
            'payment_method': data['payment_method'],
            'transaction_id': data.get('transaction_id', ''),
            'payment_status': data.get('payment_status', 'completed'),
            'payment_date': datetime.utcnow(),
            'billing_address': data.get('billing_address', {}),
            'phone': data.get('phone', user.get('phone', '')),
            'notes': data.get('notes', ''),
            'created_at': datetime.utcnow()
        }
        
        # Save payment record
        payment_result = payments_collection.insert_one(payment)
        payment_id = str(payment_result.inserted_id)
        
        # Add course to user's enrolled courses
        users_collection.update_one(
            {'_id': ObjectId(current_user_id)},
            {'$push': {'enrolled_courses': course_id}}
        )
        
        # Increment enrolled students count
        courses_collection.update_one(
            {'_id': ObjectId(course_id)},
            {'$inc': {'enrolled_students': 1}}
        )
        
        return jsonify({
            'message': 'Payment successful and enrolled in course',
            'payment_id': payment_id,
            'payment': {
                'transaction_id': payment['transaction_id'],
                'amount': payment['amount'],
                'payment_method': payment['payment_method'],
                'payment_status': payment['payment_status'],
                'payment_date': payment['payment_date'].isoformat()
            },
            'enrollment': {
                'course_id': course_id,
                'course_name': course['name'],
                'enrolled_at': datetime.utcnow().isoformat()
            }
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/review', methods=['POST'])
@jwt_required()
def add_review(course_id):
    """Add a review and rating to a course"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400
        
        data = request.get_json()
        current_user_id = get_jwt_identity()
        
        # Validate rating
        rating = data.get('rating')
        if not rating or not (1 <= rating <= 5):
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        # Get user details
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        
        # Create review
        review = {
            'user_id': current_user_id,
            'user_name': user['name'],
            'rating': rating,
            'comment': data.get('comment', ''),
            'created_at': datetime.utcnow()
        }
        
        # Add review to course
        courses_collection.update_one(
            {'_id': ObjectId(course_id)},
            {'$push': {'reviews': review}}
        )
        
        # Update ratings
        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        reviews = course.get('reviews', [])
        total_ratings = len(reviews)
        average_rating = sum(r['rating'] for r in reviews) / total_ratings if total_ratings > 0 else 0
        
        # Update rating distribution
        distribution = {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0}
        for r in reviews:
            distribution[str(r['rating'])] += 1
        
        courses_collection.update_one(
            {'_id': ObjectId(course_id)},
            {'$set': {
                'ratings.average': round(average_rating, 2),
                'ratings.count': total_ratings,
                'ratings.distribution': distribution
            }}
        )
        
        return jsonify({'message': 'Review added successfully'}), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/content/upload', methods=['POST'])
@admin_required
def upload_course_content(course_id):
    """Upload content file to a course (Admin only)"""
    try:
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400

        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        title = request.form.get('title', '').strip()
        if not title:
            return jsonify({'error': 'title is required'}), 400

        description = request.form.get('description', '').strip()

        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        video_extensions = {'mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv'}
        image_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        resource_extensions = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'zip', 'rar'}

        if file_ext in video_extensions:
            target_folder = VIDEO_FOLDER
            file_url_prefix = '/api/files/videos/'
            inferred_type = 'video'
            max_size = 100 * 1024 * 1024
        elif file_ext in image_extensions:
            target_folder = IMAGE_FOLDER
            file_url_prefix = '/api/files/images/'
            inferred_type = 'image'
            max_size = 5 * 1024 * 1024
        elif file_ext in resource_extensions:
            target_folder = RESOURCE_FOLDER
            file_url_prefix = '/api/files/resources/'
            inferred_type = 'document'
            max_size = 20 * 1024 * 1024
        else:
            return jsonify({'error': 'Unsupported file type for content upload'}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > max_size:
            return jsonify({'error': 'File size exceeds allowed limit'}), 400

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"content_{course_id}_{timestamp}_{secure_filename(file.filename)}"
        filepath = os.path.join(target_folder, unique_filename)
        file.save(filepath)

        content_id = str(ObjectId())
        content_item = {
            'content_id': content_id,
            'title': title,
            'description': description,
            'content_type': request.form.get('content_type', inferred_type),
            'file_url': f"{file_url_prefix}{unique_filename}",
            'filename': unique_filename,
            'file_size': file_size,
            'resources': [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

        courses_collection.update_one(
            {'_id': ObjectId(course_id)},
            {
                '$push': {'contents': content_item},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )

        return jsonify({
            'message': 'Course content uploaded successfully',
            'course_id': course_id,
            'content': {
                'content_id': content_id,
                'title': content_item['title'],
                'description': content_item['description'],
                'content_type': content_item['content_type'],
                'file_url': content_item['file_url'],
                'filename': content_item['filename'],
                'file_size': content_item['file_size']
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/resources/upload', methods=['POST'])
@admin_required
def upload_course_resource(course_id):
    """Upload resource file and attach to content or course (Admin only)"""
    try:
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400

        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        allowed_extensions = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'zip', 'rar', 'jpg', 'jpeg', 'png', 'webp', 'mp4'}
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Unsupported resource file type'}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 20 * 1024 * 1024:
            return jsonify({'error': 'Resource size exceeds 20MB limit'}), 400

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"resource_{course_id}_{timestamp}_{secure_filename(file.filename)}"
        filepath = os.path.join(RESOURCE_FOLDER, unique_filename)
        file.save(filepath)

        resource_id = str(ObjectId())
        resource_item = {
            'resource_id': resource_id,
            'title': request.form.get('title', secure_filename(file.filename)),
            'file_url': f"/api/files/resources/{unique_filename}",
            'filename': unique_filename,
            'file_size': file_size,
            'uploaded_at': datetime.utcnow()
        }

        content_id = request.form.get('content_id', '').strip()
        if content_id:
            result = courses_collection.update_one(
                {
                    '_id': ObjectId(course_id),
                    'contents.content_id': content_id
                },
                {
                    '$push': {'contents.$.resources': resource_item},
                    '$set': {'updated_at': datetime.utcnow()}
                }
            )

            if result.matched_count == 0:
                return jsonify({'error': 'content_id not found in this course'}), 404
        else:
            courses_collection.update_one(
                {'_id': ObjectId(course_id)},
                {
                    '$push': {'course_resources': resource_item},
                    '$set': {'updated_at': datetime.utcnow()}
                }
            )

        return jsonify({
            'message': 'Resource uploaded successfully',
            'course_id': course_id,
            'content_id': content_id if content_id else None,
            'resource': {
                'resource_id': resource_id,
                'title': resource_item['title'],
                'file_url': resource_item['file_url'],
                'filename': resource_item['filename'],
                'file_size': resource_item['file_size']
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/content', methods=['GET'])
@jwt_required()
def get_enrolled_course_content(course_id):
    """Get course content and resources for enrolled student"""
    try:
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400

        current_user_id = get_jwt_identity()
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if not is_user_enrolled(user, course_id):
            return jsonify({'error': 'You are not enrolled in this course'}), 403

        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        contents = course.get('contents', [])
        course_resources = course.get('course_resources', [])

        return jsonify({
            'course_id': course_id,
            'course_name': course.get('name', ''),
            'content_count': len(contents),
            'contents': contents,
            'course_resources': course_resources
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/progress', methods=['POST'])
@jwt_required()
def update_course_progress(course_id):
    """Update progress for an enrolled student's course"""
    try:
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400

        current_user_id = get_jwt_identity()
        data = request.get_json() or {}

        content_id = data.get('content_id', '').strip()
        if not content_id:
            return jsonify({'error': 'content_id is required'}), 400

        completed = bool(data.get('completed', True))
        current_position_seconds = data.get('current_position_seconds', 0)
        if not isinstance(current_position_seconds, (int, float)) or current_position_seconds < 0:
            return jsonify({'error': 'current_position_seconds must be a non-negative number'}), 400

        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if not is_user_enrolled(user, course_id):
            return jsonify({'error': 'You are not enrolled in this course'}), 403

        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        contents = course.get('contents', [])
        if not any(content.get('content_id') == content_id for content in contents):
            return jsonify({'error': 'content_id not found in this course'}), 404

        course_progress = user.get('course_progress', {})
        progress_entry = course_progress.get(course_id, {
            'course_id': course_id,
            'completed_content_ids': [],
            'last_content_id': '',
            'current_position_seconds': 0,
            'progress_percent': 0,
            'started_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        })

        completed_content_ids = progress_entry.get('completed_content_ids', [])
        if completed and content_id not in completed_content_ids:
            completed_content_ids.append(content_id)
        if not completed and content_id in completed_content_ids:
            completed_content_ids.remove(content_id)

        total_contents = len(contents)
        progress_percent = round((len(completed_content_ids) / total_contents) * 100, 2) if total_contents > 0 else 0

        progress_entry['completed_content_ids'] = completed_content_ids
        progress_entry['last_content_id'] = content_id
        progress_entry['current_position_seconds'] = current_position_seconds
        progress_entry['progress_percent'] = progress_percent
        progress_entry['updated_at'] = datetime.utcnow()
        if not progress_entry.get('started_at'):
            progress_entry['started_at'] = datetime.utcnow()

        course_progress[course_id] = progress_entry

        users_collection.update_one(
            {'_id': ObjectId(current_user_id)},
            {
                '$set': {
                    'course_progress': course_progress,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        return jsonify({
            'message': 'Course progress updated successfully',
            'progress': format_progress_response(progress_entry, total_contents)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/courses/<course_id>/progress', methods=['GET'])
@jwt_required()
def get_course_progress(course_id):
    """Get progress for an enrolled student's course"""
    try:
        if not ObjectId.is_valid(course_id):
            return jsonify({'error': 'Invalid course ID'}), 400

        current_user_id = get_jwt_identity()
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if not is_user_enrolled(user, course_id):
            return jsonify({'error': 'You are not enrolled in this course'}), 403

        course = courses_collection.find_one({'_id': ObjectId(course_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404

        total_contents = len(course.get('contents', []))
        progress_entry = user.get('course_progress', {}).get(course_id, {
            'course_id': course_id,
            'completed_content_ids': [],
            'last_content_id': '',
            'current_position_seconds': 0,
            'progress_percent': 0,
            'started_at': None,
            'updated_at': None
        })

        return jsonify({
            'course_id': course_id,
            'course_name': course.get('name', ''),
            'progress': format_progress_response(progress_entry, total_contents)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Payment Routes ====================

@app.route('/api/payments/my-payments', methods=['GET'])
@jwt_required()
def get_my_payments():
    """Get payment history for current user"""
    try:
        current_user_id = get_jwt_identity()
        
        # Get all payments for current user
        payments = list(payments_collection.find({'user_id': current_user_id}).sort('payment_date', -1))
        
        # Serialize payments
        for payment in payments:
            serialize_doc(payment)
        
        return jsonify({
            'count': len(payments),
            'payments': payments
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payments/<payment_id>', methods=['GET'])
@jwt_required()
def get_payment_details(payment_id):
    """Get specific payment details"""
    try:
        # Validate ObjectId
        if not ObjectId.is_valid(payment_id):
            return jsonify({'error': 'Invalid payment ID'}), 400
        
        current_user_id = get_jwt_identity()
        user = users_collection.find_one({'_id': ObjectId(current_user_id)})
        
        # Find payment
        payment = payments_collection.find_one({'_id': ObjectId(payment_id)})
        if not payment:
            return jsonify({'error': 'Payment not found'}), 404
        
        # Check if user has permission to view this payment
        # Users can only view their own payments, admins can view all
        if payment['user_id'] != current_user_id and user.get('role') != 'admin':
            return jsonify({'error': 'Access denied'}), 403
        
        return jsonify({'payment': serialize_doc(payment)}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Admin Routes ====================

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_stats():
    """Get dashboard statistics (Admin only)"""
    try:
        total_students = users_collection.count_documents({'role': 'student'})
        total_courses = courses_collection.count_documents({})
        active_courses = courses_collection.count_documents({'status': 'active'})
        
        # Get total enrollments
        total_enrollments = 0
        for course in courses_collection.find():
            total_enrollments += course.get('enrolled_students', 0)
        
        # Get total payments and revenue
        total_payments = payments_collection.count_documents({})
        pipeline = [
            {'$group': {'_id': None, 'total_revenue': {'$sum': '$amount'}}}
        ]
        revenue_result = list(payments_collection.aggregate(pipeline))
        total_revenue = revenue_result[0]['total_revenue'] if revenue_result else 0
        
        return jsonify({
            'stats': {
                'total_students': total_students,
                'total_courses': total_courses,
                'active_courses': active_courses,
                'total_enrollments': total_enrollments,
                'total_payments': total_payments,
                'total_revenue': round(total_revenue, 2)
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users (Admin only)"""
    try:
        users = list(users_collection.find())
        
        # Serialize and remove passwords
        for user in users:
            serialize_doc(user)
            user.pop('password', None)
        
        return jsonify({
            'count': len(users),
            'users': users
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/payments', methods=['GET'])
@admin_required
def get_all_payments():
    """Get all payments with optional filters (Admin only)"""
    try:
        # Get query parameters
        payment_status = request.args.get('payment_status')
        course_id = request.args.get('course_id')
        user_id = request.args.get('user_id')
        
        # Build query
        query = {}
        if payment_status:
            query['payment_status'] = payment_status
        if course_id:
            query['course_id'] = course_id
        if user_id:
            query['user_id'] = user_id
        
        # Get payments
        payments = list(payments_collection.find(query).sort('payment_date', -1))
        
        # Serialize payments
        for payment in payments:
            serialize_doc(payment)
        
        return jsonify({
            'count': len(payments),
            'payments': payments
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Health Check ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'iLearn API is running',
        'timestamp': datetime.utcnow().isoformat()
    }), 200

# ==================== File Upload Routes ====================

@app.route('/api/upload/image', methods=['POST'])
@jwt_required()
def upload_image():
    """Upload an image file and store on disk"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        # Validate file
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file type by extension
        allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Only image files allowed (JPG, PNG, GIF, WebP)'}), 400
        
        # Check file size (max 5MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'Image size exceeds 5MB limit'}), 400
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"img_{timestamp}_{secure_filename(file.filename)}"
        filepath = os.path.join(IMAGE_FOLDER, unique_filename)
        
        # Save file
        file.save(filepath)
        
        # Return file path for database storage
        file_url = f"/api/files/images/{unique_filename}"
        
        return jsonify({
            'message': 'Image uploaded successfully',
            'file_url': file_url,
            'filename': unique_filename,
            'size': file_size
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload/video', methods=['POST'])
@jwt_required()
def upload_video():
    """Upload a video file and store on disk"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        # Validate file
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file type by extension
        allowed_extensions = {'mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Only video files allowed (MP4, WebM, Ogg, MOV, AVI, MKV)'}), 400
        
        # Check file size (max 100MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 100 * 1024 * 1024:
            return jsonify({'error': 'Video size exceeds 100MB limit'}), 400
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"vid_{timestamp}_{secure_filename(file.filename)}"
        filepath = os.path.join(VIDEO_FOLDER, unique_filename)
        
        # Save file
        file.save(filepath)
        
        # Return file path for database storage
        file_url = f"/api/files/videos/{unique_filename}"
        
        return jsonify({
            'message': 'Video uploaded successfully',
            'file_url': file_url,
            'filename': unique_filename,
            'size': file_size
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== File Retrieval Routes ====================

@app.route('/api/files/images/<filename>', methods=['GET'])
def get_image(filename):
    """Retrieve uploaded image"""
    try:
        # Security: prevent directory traversal
        filename = secure_filename(filename)
        filepath = os.path.join(IMAGE_FOLDER, filename)
        
        # Check if file exists
        if not os.path.exists(filepath):
            return jsonify({'error': 'Image not found'}), 404
        
        return send_file(filepath, mimetype='image/jpeg')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/resources/<filename>', methods=['GET'])
def get_resource_file(filename):
    """Retrieve uploaded resource file"""
    try:
        filename = secure_filename(filename)
        filepath = os.path.join(RESOURCE_FOLDER, filename)

        if not os.path.exists(filepath):
            return jsonify({'error': 'Resource file not found'}), 404

        return send_file(filepath, as_attachment=False)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/videos/<filename>', methods=['GET'])
def get_video(filename):
    """Retrieve uploaded video with streaming support"""
    try:
        # Security: prevent directory traversal
        filename = secure_filename(filename)
        filepath = os.path.join(VIDEO_FOLDER, filename)
        
        # Check if file exists
        if not os.path.exists(filepath):
            return jsonify({'error': 'Video not found'}), 404
        
        # Get file size for range requests
        file_size = os.path.getsize(filepath)
        
        # Handle range requests (for streaming)
        range_header = request.headers.get('Range')
        if range_header:
            range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                
                with open(filepath, 'rb') as f:
                    f.seek(start)
                    data = f.read(end - start + 1)
                
                response = app.make_response(data)
                response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                response.headers['Accept-Ranges'] = 'bytes'
                response.headers['Content-Length'] = len(data)
                response.status_code = 206
                response.headers['Content-Type'] = 'video/mp4'
                return response
        
        return send_file(filepath, mimetype='video/mp4')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Root Endpoint ====================

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'message': 'Welcome to iLearn API',
        'version': '1.0.0',
        'endpoints': {
            'auth': {
                'register': 'POST /api/auth/register',
                'login': 'POST /api/auth/login',
                'profile': 'GET /api/auth/profile',
                'upload_profile_photo': 'POST /api/auth/profile/photo'
            },
            'courses': {
                'create': 'POST /api/courses (admin)',
                'list': 'GET /api/courses',
                'get': 'GET /api/courses/<id>',
                'update': 'PUT /api/courses/<id> (admin)',
                'delete': 'DELETE /api/courses/<id> (admin)',
                'enroll': 'POST /api/courses/<id>/enroll',
                'enroll_with_payment': 'POST /api/courses/<id>/enroll-with-payment',
                'review': 'POST /api/courses/<id>/review',
                'upload_content': 'POST /api/courses/<id>/content/upload (admin)',
                'upload_resource': 'POST /api/courses/<id>/resources/upload (admin)',
                'get_content': 'GET /api/courses/<id>/content (enrolled student)',
                'update_progress': 'POST /api/courses/<id>/progress (enrolled student)',
                'get_progress': 'GET /api/courses/<id>/progress (enrolled student)'
            },
            'payments': {
                'my_payments': 'GET /api/payments/my-payments',
                'get_payment': 'GET /api/payments/<payment_id>'
            },
            'admin': {
                'stats': 'GET /api/admin/stats (admin)',
                'users': 'GET /api/admin/users (admin)',
                'payments': 'GET /api/admin/payments (admin)'
            },
            'upload': {
                'image': 'POST /api/upload/image',
                'video': 'POST /api/upload/video'
            },
            'files': {
                'get_image': 'GET /api/files/images/<filename>',
                'get_video': 'GET /api/files/videos/<filename>',
                'get_resource': 'GET /api/files/resources/<filename>'
            }
        }
    }), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
