import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pydantic import BaseModel

# Data file paths
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")
RESPONSES_FILE = os.path.join(DATA_DIR, "responses.json")

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

# Pydantic Models
class User(BaseModel):
    id: int
    username: str
    full_name: str
    xp: int = 0
    coins: int = 0
    streak: int = 0
    level: int = 1
    last_active: datetime
    daily_goal: int = 20
    daily_xp: int = 0
    total_lessons_completed: int = 0
    achievements: List[str] = []
    created_at: datetime = datetime.utcnow()

class CourseProgress(BaseModel):
    user_id: int
    course_id: str
    lesson_id: int
    completed: bool = False
    score: int = 0
    completed_at: Optional[datetime] = None
    time_spent: int = 0  # seconds

class UserResponse(BaseModel):
    user_id: int
    course_id: str
    lesson_id: int
    question_index: int
    answer_index: int
    is_correct: bool
    response_time: int  # seconds
    timestamp: datetime = datetime.utcnow()

# Database storage classes
class DataStorage:
    @staticmethod
    def load_json(file_path: str, default: dict = None) -> dict:
        """Load data from JSON file"""
        if default is None:
            default = {}
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert datetime strings back to datetime objects
                    if file_path == USERS_FILE:
                        for user_id, user_data in data.items():
                            if 'last_active' in user_data:
                                user_data['last_active'] = datetime.fromisoformat(user_data['last_active'])
                            if 'created_at' in user_data:
                                user_data['created_at'] = datetime.fromisoformat(user_data['created_at'])
                    elif file_path == PROGRESS_FILE:
                        for key, progress_data in data.items():
                            if 'completed_at' in progress_data and progress_data['completed_at']:
                                progress_data['completed_at'] = datetime.fromisoformat(progress_data['completed_at'])
                    elif file_path == RESPONSES_FILE:
                        for response_data in data.values():
                            if 'timestamp' in response_data:
                                response_data['timestamp'] = datetime.fromisoformat(response_data['timestamp'])
                    return data
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
                return default
        return default

    @staticmethod
    def save_json(file_path: str, data: dict):
        """Save data to JSON file"""
        # Convert datetime objects to strings
        data_to_save = json.loads(json.dumps(data, default=str, ensure_ascii=False))
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)

# In-memory databases (will be synced with files)
users_db: Dict[int, User] = {}
courses_progress_db: Dict[str, CourseProgress] = {}
user_responses_db: Dict[str, UserResponse] = {}

# Load data from files on startup
def load_all_data():
    """Load all data from JSON files"""
    global users_db, courses_progress_db, user_responses_db
    
    # Load users
    users_data = DataStorage.load_json(USERS_FILE, {})
    users_db = {int(k): User(**v) for k, v in users_data.items()}
    
    # Load progress
    progress_data = DataStorage.load_json(PROGRESS_FILE, {})
    courses_progress_db = {k: CourseProgress(**v) for k, v in progress_data.items()}
    
    # Load responses
    responses_data = DataStorage.load_json(RESPONSES_FILE, {})
    user_responses_db = {k: UserResponse(**v) for k, v in responses_data.items()}

def save_all_data():
    """Save all data to JSON files"""
    # Convert users to dict
    users_data = {str(uid): user.dict() for uid, user in users_db.items()}
    DataStorage.save_json(USERS_FILE, users_data)
    
    # Convert progress to dict
    progress_data = {k: progress.dict() for k, progress in courses_progress_db.items()}
    DataStorage.save_json(PROGRESS_FILE, progress_data)
    
    # Convert responses to dict
    responses_data = {k: response.dict() for k, response in user_responses_db.items()}
    DataStorage.save_json(RESPONSES_FILE, responses_data)

def save_user(user_id: int):
    """Save a single user to file"""
    if user_id in users_db:
        users_data = DataStorage.load_json(USERS_FILE, {})
        users_data[str(user_id)] = users_db[user_id].dict()
        DataStorage.save_json(USERS_FILE, users_data)

def save_progress(course_key: str):
    """Save a single progress entry to file"""
    if course_key in courses_progress_db:
        progress_data = DataStorage.load_json(PROGRESS_FILE, {})
        progress_data[course_key] = courses_progress_db[course_key].dict()
        DataStorage.save_json(PROGRESS_FILE, progress_data)

def save_response(response_key: str):
    """Save a single response to file"""
    if response_key in user_responses_db:
        responses_data = DataStorage.load_json(RESPONSES_FILE, {})
        responses_data[response_key] = user_responses_db[response_key].dict()
        DataStorage.save_json(RESPONSES_FILE, responses_data)

# Initialize data on import
load_all_data()

# Programming courses data
PROGRAMMING_COURSES = [
    {
        "id": "html",
        "title": "HTML для начинающих",
        "description": "Научись создавать веб-страницы с нуля",
        "icon": "fa-html5",
        "type": "html",
        "lessons_count": 3
    },
    {
        "id": "python",
        "title": "Python для начинающих",
        "description": "Основы программирования на Python",
        "icon": "fa-python",
        "type": "python",
        "lessons_count": 3
    },
    {
        "id": "roblox",
        "title": "Разработка игр в Roblox",
        "description": "Создай свою первую игру в Roblox Studio",
        "icon": "fa-gamepad",
        "type": "roblox",
        "lessons_count": 3
    }
]

# Helper functions
def calculate_level(xp: int) -> int:
    """Calculate user level based on XP"""
    return max(1, 1 + (xp // 100))  # 100 XP per level, level 1 starts at 0 XP

def calculate_xp_for_next_level(current_level: int) -> int:
    """Calculate XP needed for next level (always 100 XP per level)"""
    return 100

def reset_daily_stats(user: User):
    """Reset daily stats if it's a new day"""
    today = datetime.utcnow().date()
    last_active_date = user.last_active.date() if isinstance(user.last_active, datetime) else user.last_active
    
    if last_active_date < today:
        # Check if streak should continue
        if last_active_date == today - timedelta(days=1):
            # Streak continues
            pass
        else:
            # Streak broken
            user.streak = 1
        
        # Reset daily XP
        user.daily_xp = 0

