# Tool functions for the restaurant reservation chatbot
import json
import os
from typing import Optional, List, Dict, Any
import sqlite3
from datetime import datetime

# Global variables
ALL_RESTAURANTS = []
MVP_TAG_LIST = []
DB_PATH = "bookings.db"

# Load restaurant data
def load_restaurants():
    """Load restaurant data from restaurant.json"""
    with open('restaurant.json', 'r') as f:
        return json.load(f)

# Load restaurant data
ALL_RESTAURANTS = load_restaurants()

# Generate unique tag list from restaurant data
def generate_tag_list():
    """Generate a list of all unique tags across all restaurants"""
    tags = set()
    for restaurant in ALL_RESTAURANTS:
        tags.update(restaurant['tags'])
    return sorted(list(tags))

# Generate the tag list
MVP_TAG_LIST = generate_tag_list()

# Initialize database
def init_database():
    """
    Initialize the SQLite database with a reservations table.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create reservations table if it doesn't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id TEXT NOT NULL,
        booking_date TEXT NOT NULL,
        booking_time TEXT NOT NULL,
        party_size INTEGER NOT NULL,
        user_name TEXT NOT NULL,
        user_phone TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def find_restaurant(name: Optional[str] = None, location: Optional[str] = None, tags: Optional[List[str]] = None, party_size: Optional[int] = None) -> str:
    """
    Find restaurants based on name, location, tags, and/or party size.
    
    Args:
        name: Optional name of the restaurant (partial match)
        location: Optional location (partial match)
        tags: Optional list of tags to filter by
        party_size: Optional number of people in the party (filters for restaurants with enough capacity)
        
    Returns:
        String with JSON array of matching restaurants
    """
    matches = []
    
    for restaurant in ALL_RESTAURANTS:
        # Initialize as a match
        is_match = True
        
        # Filter by name if provided
        if name and name.lower() not in restaurant['name'].lower():
            is_match = False
            
        # Filter by location if provided
        if location and is_match:
            if location.lower() not in restaurant['location'].lower():
                is_match = False
        
        # Filter by tags if provided
        if tags and is_match:
            # Check if restaurant has at least one of the requested tags
            if not any(tag.lower() in [t.lower() for t in restaurant['tags']] for tag in tags):
                is_match = False
        
        # Filter by party size if provided
        if party_size and is_match:
            if party_size <= 0:
                is_match = False
            elif party_size > restaurant['capacity']:
                is_match = False
        
        # Add to matches if all criteria passed
        if is_match:
            matches.append(restaurant)
    
    # Format the response
    if not matches:
        return json.dumps({"result": "No restaurants found matching your criteria."})
    
    # Return formatted results
    result_data = []
    for restaurant in matches:
        result_data.append({
            "id": restaurant["id"],
            "name": restaurant["name"],
            "tags": restaurant["tags"],
            "location": restaurant["location"],
            "capacity": restaurant["capacity"]
        })
    
    return json.dumps({"result": result_data})

def check_availability(restaurant_id: str, date: str, time: str, party_size: int) -> str:
    """
    Check if a table is available for the given restaurant, date, time, and party size.
    
    Args:
        restaurant_id: ID of the restaurant
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format
        party_size: Number of people
        
    Returns:
        String with JSON availability result
    """
    # Validate party size first
    if party_size <= 0:
        return json.dumps({
            "available": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "message": f"Party size must be a positive number."
        })
    
    # Validate restaurant_id
    restaurant = None
    for r in ALL_RESTAURANTS:
        if r["id"] == restaurant_id:
            restaurant = r
            break
    
    if not restaurant:
        return json.dumps({
            "available": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "message": f"Restaurant with ID {restaurant_id} not found."
        })
    
    # Get restaurant capacity
    restaurant_capacity = restaurant["capacity"]
    
    # Check if party size exceeds total restaurant capacity
    if party_size > restaurant_capacity:
        return json.dumps({
            "available": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "message": f"Sorry, this restaurant can only accommodate up to {restaurant_capacity} people in total."
        })
    
    # Round time to the nearest hour (HH:00)
    from utils import round_time_to_nearest_hour
    rounded_time = round_time_to_nearest_hour(time)
    
    if not rounded_time:
        return json.dumps({
            "available": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "message": f"Invalid time format. Please use HH:MM format."
        })
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check existing bookings for this time slot
    cursor.execute('''
    SELECT SUM(party_size) as total_booked
    FROM reservations
    WHERE restaurant_id = ? AND booking_date = ? AND booking_time = ?
    ''', (restaurant_id, date, rounded_time))
    
    result = cursor.fetchone()
    conn.close()
    
    # Calculate total booked
    total_booked = result[0] if result[0] is not None else 0
    
    # Check if there's enough capacity
    available_capacity = restaurant_capacity - total_booked
    is_available = available_capacity >= party_size
    
    message = ""
    if is_available:
        message = "Tables are available at this time!"
    elif total_booked == restaurant_capacity:
        message = f"Sorry, the restaurant is fully booked at {rounded_time}."
    elif available_capacity > 0:
        message = f"Sorry, we only have space for {available_capacity} more people at {rounded_time}, not {party_size}."
    else:
        message = f"Sorry, we don't have availability for {party_size} people at {rounded_time}."
    
    return json.dumps({
        "available": is_available,
        "restaurant_id": restaurant_id,
        "date": date,
        "time": rounded_time,
        "party_size": party_size,
        "restaurant_capacity": restaurant_capacity,
        "available_capacity": available_capacity,
        "message": message
    })

def make_reservation(restaurant_id: str, date: str, time: str, party_size: int, user_name: str, user_phone: str) -> str:
    """
    Make a reservation if a table is available.
    
    Args:
        restaurant_id: ID of the restaurant
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format
        party_size: Number of people
        user_name: Name of the person making the reservation
        user_phone: Phone number of the person
        
    Returns:
        String with JSON reservation result
    """
    # Validate inputs
    if not user_name or not user_phone:
        return json.dumps({
            "success": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "user_name": user_name,
            "user_phone": user_phone,
            "message": "Name and phone number are required for reservation."
        })
    
    # First check availability
    availability_result = json.loads(check_availability(restaurant_id, date, time, party_size))
    
    if not availability_result["available"]:
        return json.dumps({
            "success": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
            "user_name": user_name,
            "user_phone": user_phone,
            "message": availability_result["message"]
        })
    
    # Use the rounded time from availability check
    rounded_time = availability_result["time"]
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Begin transaction and use a lock for this operation
        conn.isolation_level = 'EXCLUSIVE'
        conn.execute('BEGIN EXCLUSIVE')
        cursor = conn.cursor()
        
        # Double-check availability within transaction to prevent race conditions
        cursor.execute('''
        SELECT SUM(party_size) as total_booked
        FROM reservations
        WHERE restaurant_id = ? AND booking_date = ? AND booking_time = ?
        ''', (restaurant_id, date, rounded_time))
        
        result = cursor.fetchone()
        total_booked = result[0] if result[0] is not None else 0
        
        # Get restaurant capacity again
        restaurant = None
        for r in ALL_RESTAURANTS:
            if r["id"] == restaurant_id:
                restaurant = r
                break
        
        restaurant_capacity = restaurant["capacity"]
        available_capacity = restaurant_capacity - total_booked
        
        # Final availability check
        if available_capacity < party_size:
            conn.rollback()
            return json.dumps({
                "success": False,
                "restaurant_id": restaurant_id,
                "date": date,
                "time": rounded_time,
                "party_size": party_size,
                "user_name": user_name,
                "user_phone": user_phone,
                "message": f"Sorry, the restaurant became fully booked while processing your reservation. Only {available_capacity} seats available."
            })
        
        # Insert reservation
        cursor.execute('''
        INSERT INTO reservations 
        (restaurant_id, booking_date, booking_time, party_size, user_name, user_phone)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (restaurant_id, date, rounded_time, party_size, user_name, user_phone))
        
        # Get the ID of the new reservation
        reservation_id = cursor.lastrowid
        
        conn.commit()
        
        # Find restaurant name
        restaurant_name = restaurant["name"]
        
        return json.dumps({
            "success": True,
            "reservation_id": f"res{reservation_id}",
            "restaurant_id": restaurant_id,
            "restaurant_name": restaurant_name,
            "date": date,
            "time": rounded_time,
            "party_size": party_size,
            "user_name": user_name,
            "user_phone": user_phone,
            "message": f"Your reservation at {restaurant_name} for {party_size} people on {date} at {rounded_time} has been confirmed!"
        })
        
    except Exception as e:
        conn.rollback()
        return json.dumps({
            "success": False,
            "restaurant_id": restaurant_id,
            "date": date,
            "time": rounded_time,
            "party_size": party_size,
            "user_name": user_name,
            "user_phone": user_phone,
            "message": f"Failed to make reservation: {str(e)}"
        })
    finally:
        conn.close()

# Tool mapping
tool_map = {
    "find_restaurant": find_restaurant,
    "check_availability": check_availability,
    "make_reservation": make_reservation
}

# Initialize database connection and load restaurant data
def initialize():
    """
    Initialize the database and load restaurant data.
    """
    init_database()
    load_restaurants()

# Initialize when module is imported
initialize()
