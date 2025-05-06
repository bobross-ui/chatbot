# Helper functions for the chatbot
from typing import Optional
import re

def format_history_for_gemma(messages, initial_instructions):
    """
    Format message history for Gemma.
    
    Takes the internal message history list and initial instructions,
    returns a single string formatted with <start_of_turn>role, <end_of_turn>\n,
    embedding initial instructions correctly in the first user turn.
    
    Args:
        messages (list): List of message dictionaries with 'role' and 'content' keys
        initial_instructions (str): Initial instructions to give to the LLM
        
    Returns:
        str: Formatted history string for Gemma
    """
    formatted_history = ""
    
    # Handle empty message history
    if not messages or len(messages) == 0:
        # Just create a user turn with instructions
        formatted_history = f"<start_of_turn>user\n{initial_instructions}<end_of_turn>\n<start_of_turn>model\n"
        return formatted_history
    
    # Find the first user message to embed instructions
    first_user_msg_idx = -1
    for i, message in enumerate(messages):
        if message["role"] == "user":
            first_user_msg_idx = i
            break
    
    # If no user message found, just use the first message
    if first_user_msg_idx == -1:
        first_user_msg_idx = 0
    
    # Process all messages
    for i, message in enumerate(messages):
        # Map roles: assistant -> model, system -> user (should be rare)
        role = "model" if message["role"] == "assistant" else "user"
        
        # For the first user message, include the initial instructions
        if i == first_user_msg_idx and role == "user":
            # Combine instructions and user content properly
            content = f"{initial_instructions}\n{message['content']}"
        else:
            content = message["content"]
        
        # Add formatted message with proper newline handling
        formatted_history += f"<start_of_turn>{role}\n{content}<end_of_turn>\n"
    
    # Ensure the last turn sets up for model response if needed
    last_message = messages[-1]
    formatted_history += "<start_of_turn>model\n"
    
    return formatted_history

def round_time_to_nearest_hour(time_str: str) -> Optional[str]:
    """
    Rounds a time string in HH:MM format to the nearest hour (HH:00).
    
    Args:
        time_str: Time string in HH:MM (24-hour) format
        
    Returns:
        Rounded time string in HH:00 format, or None if invalid format
    """
    # Check if the time string matches the expected format
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        return None
    
    try:
        # Parse the time string
        hours, minutes = map(int, time_str.split(':'))
        
        # Validate hours and minutes
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return None
        
        # Round to the nearest hour
        if minutes >= 30:
            hours = (hours + 1) % 24
            
        # Return the rounded time
        return f"{hours:02d}:00"
    except Exception:
        return None
