import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException, Depends, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import uvicorn
import threading
import nest_asyncio
from models import (
    User, CourseProgress, UserResponse, 
    users_db, courses_progress_db, user_responses_db, PROGRAMMING_COURSES,
    save_user, save_progress, save_response, save_all_data, load_all_data,
    calculate_level, calculate_xp_for_next_level, reset_daily_stats
)

# Initialize FastAPI app
app = FastAPI(title="CodeKids API", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=".")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BOT_TOKEN = "8541683580:AAEKE77zU8LwUgsTp6G-e1nqLLPG47ORlkY"
SECRET_KEY = "your-secret-key-here"  # Change this in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

# Web app URL (using your ngrok URL or localhost for development)
web_app_url = "http://localhost:8000"  # Update this with your actual URL

# JWT Token functions
def create_access_token(data: dict):
    from jose import jwt
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Command handler for /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Load fresh data
    load_all_data()
    
    # Create or update user in database
    if user_id not in users_db:
        users_db[user_id] = User(
            id=user_id,
            username=user.username or f"user_{user_id}",
            full_name=user.full_name or "User",
            xp=0,
            coins=100,  # Starting coins
            streak=0,
            level=1,
            last_active=datetime.utcnow(),
            daily_goal=20,
            daily_xp=0,
            total_lessons_completed=0,
            achievements=[],
            created_at=datetime.utcnow()
        )
        save_user(user_id)
    else:
        # Reset daily stats if needed
        reset_daily_stats(users_db[user_id])
        users_db[user_id].last_active = datetime.utcnow()
        users_db[user_id].level = calculate_level(users_db[user_id].xp)
        save_user(user_id)
    
    # Create auth token
    access_token = create_access_token(data={"sub": str(user_id)})
    app_url = f"{web_app_url}?token={access_token}"
    
    # Create a web app button
    keyboard = [
        [InlineKeyboardButton("🚀 Начать обучение", web_app=WebAppInfo(url=app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {user.full_name}! 🎉\n\nНажмите кнопку ниже, чтобы начать обучение программированию:",
        reply_markup=reply_markup
    )

# API Endpoints
@app.get("/api/courses")
async def get_courses():
    """Get all available courses"""
    load_all_data()
    return {"courses": PROGRAMMING_COURSES}

@app.get("/api/user/{user_id}")
async def get_user(user_id: int):
    """Get user data"""
    load_all_data()
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users_db[user_id]
    reset_daily_stats(user)
    user.level = calculate_level(user.xp)
    user.last_active = datetime.utcnow()
    
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "xp": user.xp,
        "coins": user.coins,
        "streak": user.streak,
        "level": user.level,
        "daily_goal": user.daily_goal,
        "daily_xp": user.daily_xp,
        "total_lessons_completed": user.total_lessons_completed,
        "achievements": user.achievements,
        "xp_for_next_level": calculate_xp_for_next_level(user.level),
        "last_active": user.last_active.isoformat()
    }

@app.get("/api/progress/{user_id}")
async def get_user_progress(user_id: int):
    """Get user progress for all courses"""
    load_all_data()
    user_progress = {}
    for course_key, progress in courses_progress_db.items():
        if progress.user_id == user_id:
            user_progress[course_key] = {
                "user_id": progress.user_id,
                "course_id": progress.course_id,
                "lesson_id": progress.lesson_id,
                "completed": progress.completed,
                "score": progress.score,
                "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
                "time_spent": progress.time_spent
            }
    return user_progress

@app.get("/api/progress/{user_id}/{course_id}")
async def get_course_progress(user_id: int, course_id: str):
    """Get user progress for a specific course"""
    load_all_data()
    course_progress = []
    for course_key, progress in courses_progress_db.items():
        if progress.user_id == user_id and progress.course_id == course_id:
            course_progress.append({
                "lesson_id": progress.lesson_id,
                "completed": progress.completed,
                "score": progress.score,
                "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
                "time_spent": progress.time_spent
            })
    return {"course_id": course_id, "progress": course_progress}

@app.post("/api/progress")
async def update_progress(progress: CourseProgress):
    """Update user progress"""
    load_all_data()
    course_key = f"{progress.user_id}_{progress.course_id}_{progress.lesson_id}"
    
    # Check if this is a new completion
    was_completed = False
    if course_key in courses_progress_db:
        was_completed = courses_progress_db[course_key].completed
    
    progress.completed_at = datetime.utcnow() if progress.completed else None
    courses_progress_db[course_key] = progress
    save_progress(course_key)
    
    xp_gained = 0
    achievements_to_add = []
    
    # Update user stats if lesson was completed
    if progress.completed and not was_completed:
        if progress.user_id in users_db:
            user = users_db[progress.user_id]
            
            # Award XP based on score
            xp_gained = 10 + (progress.score // 10)  # Base 10 XP + bonus for score
            user.xp += xp_gained
            user.daily_xp += xp_gained
            user.coins += 5  # Coins reward
            user.total_lessons_completed += 1
            user.level = calculate_level(user.xp)
            
            # Update streak
            today = datetime.utcnow().date()
            last_active_date = user.last_active.date() if isinstance(user.last_active, datetime) else user.last_active
            
            if last_active_date == today - timedelta(days=1):
                user.streak += 1
            elif last_active_date < today - timedelta(days=1):
                user.streak = 1
            
            user.last_active = datetime.utcnow()
            
            # Check for achievements
            if user.streak == 7 and "7_day_streak" not in user.achievements:
                achievements_to_add.append("7_day_streak")
            if user.streak == 30 and "30_day_streak" not in user.achievements:
                achievements_to_add.append("30_day_streak")
            if user.total_lessons_completed == 10 and "10_lessons" not in user.achievements:
                achievements_to_add.append("10_lessons")
            if user.level >= 5 and "level_5" not in user.achievements:
                achievements_to_add.append("level_5")
            
            user.achievements.extend(achievements_to_add)
            save_user(progress.user_id)
    
    return {
        "status": "success", 
        "message": "Progress updated",
        "xp_gained": xp_gained,
        "achievements": achievements_to_add
    }

@app.post("/api/response")
async def save_response_data(response: UserResponse):
    """Save user quiz response"""
    load_all_data()
    response_key = f"{response.user_id}_{response.course_id}_{response.lesson_id}_{response.question_index}_{uuid.uuid4().hex[:8]}"
    response.timestamp = datetime.utcnow()
    user_responses_db[response_key] = response
    save_response(response_key)
    return {"status": "success", "message": "Response saved"}

@app.get("/api/stats/{user_id}")
async def get_user_stats(user_id: int):
    """Get comprehensive user statistics"""
    load_all_data()
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users_db[user_id]
    reset_daily_stats(user)
    user.level = calculate_level(user.xp)
    
    # Calculate course statistics
    course_stats = {}
    for course in PROGRAMMING_COURSES:
        completed_lessons = 0
        total_score = 0
        total_time = 0
        
        for course_key, progress in courses_progress_db.items():
            if progress.user_id == user_id and progress.course_id == course["id"]:
                if progress.completed:
                    completed_lessons += 1
                    total_score += progress.score
                    total_time += progress.time_spent
        
        course_stats[course["id"]] = {
            "completed": completed_lessons,
            "total": course["lessons_count"],
            "progress": int((completed_lessons / course["lessons_count"]) * 100) if course["lessons_count"] > 0 else 0,
            "average_score": int(total_score / completed_lessons) if completed_lessons > 0 else 0,
            "total_time": total_time
        }
    
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "xp": user.xp,
            "coins": user.coins,
            "streak": user.streak,
            "level": user.level,
            "daily_goal": user.daily_goal,
            "daily_xp": user.daily_xp,
            "total_lessons_completed": user.total_lessons_completed,
            "achievements": user.achievements,
            "xp_for_next_level": calculate_xp_for_next_level(user.level),
            "daily_goal_progress": int((user.daily_xp / user.daily_goal) * 100) if user.daily_goal > 0 else 0
        },
        "courses": course_stats
    }

# Mini app endpoint
@app.get("/", response_class=HTMLResponse)
async def mini_app(request: Request, token: str = None):
    if not token:
        return HTMLResponse("""
            <html><body>
                <h1>Добро пожаловать в CodeDuo!</h1>
                <p>Пожалуйста, откройте это приложение через Telegram бота.</p>
                <p>Используйте команду /start в нашем боте, чтобы начать.</p>
            </body></html>
        """)
    
    try:
        from jose import jwt
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        if user_id not in users_db:
            raise HTTPException(status_code=400, detail="User not found")
    except:
        return HTMLResponse("""
            <html><body>
                <h1>Ошибка авторизации</h1>
                <p>Неверный или устаревший токен. Пожалуйста, откройте приложение заново через Telegram бота.</p>
            </body></html>
        """, status_code=401)
    
    # Serve the main app
    return HTMLResponse(content=open("index.html", "r", encoding="utf-8").read(), media_type="text/html")

def run_fastapi():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

def start_bot():
    # Set up the bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    
    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    # Start FastAPI in a separate thread
    fastapi_thread = threading.Thread(target=run_fastapi)
    fastapi_thread.daemon = True
    fastapi_thread.start()
    
    # Start the bot
    start_bot()