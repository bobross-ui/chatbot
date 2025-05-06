import streamlit as st
import os
import re
import json
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai import types
import prompts
import utils
import tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get API key from environment variables
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("Error: GEMINI_API_KEY not found in environment variables. Please add it to your .env file.")
    st.stop()

# Configure the genai client
genai.configure(api_key=api_key)

# Choose a specific Gemma model
MODEL_NAME = "gemma-3-27b-it"  # This will be reviewed and potentially changed in Phase 5

# Maximum number of sequential tool calls
MAX_SEQUENTIAL_CALLS = 4

# Function to clean response text
def clean_response_text(text):
    """Remove any formatting tags and unwanted formatting from the response text."""
    # Remove <end_of_turn> from the end of the response if present
    text = re.sub(r'<end_of_turn>\s*$', '', text)
    # Remove any other Gemma formatting tags that might appear
    text = re.sub(r'<start_of_turn>model\s*', '', text)
    text = re.sub(r'<start_of_turn>user\s*', '', text)
    # Remove parentheses wrapping the entire response
    text = re.sub(r'^\s*\((.*)\)\s*$', r'\1', text)
    return text.strip()

# Function to extract function call from LLM response
def extract_function_call(text):
    """
    Extract function call information from the LLM response.
    Returns None if no function call is detected.
    """
    # Look for JSON object with function_call
    try:
        # Try to find JSON object
        match = re.search(r'\{.*"function_call".*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            # Parse JSON
            function_call_data = json.loads(json_str)
            return function_call_data.get("function_call")
        return None
    except (json.JSONDecodeError, AttributeError):
        return None

# Set page configuration
st.set_page_config(page_title="Restaurant Reservation Bot", layout="wide")

# App title
st.title("Restaurant Reservation Bot (MVP)")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Add a welcome message to display, but don't include in LLM context
    st.session_state.messages.append({"role": "assistant", "content": "Welcome to the Restaurant Reservation Bot! How can I help you today?", "display_only": True})

# Initialize LLM conversation history for tracking separate from display
if "llm_messages" not in st.session_state:
    st.session_state.llm_messages = []

# Display prior chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Get user input
if user_input := st.chat_input("Your message:"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Add to LLM conversation history
    st.session_state.llm_messages.append({"role": "user", "content": user_input})
    
    # Display user message
    with st.chat_message("user"):
        st.write(user_input)
    
    # Set up for sequential tool calling
    tool_call_count = 0
    final_assistant_response = None
    
    # Create Gemma model instance
    model = genai.GenerativeModel(MODEL_NAME)
    
    # Sequential tool calling loop
    while tool_call_count < MAX_SEQUENTIAL_CALLS:
        # Format the message history for Gemma (using only LLM messages)
        formatted_history = utils.format_history_for_gemma(
            st.session_state.llm_messages, 
            prompts.AGENT_INITIAL_INSTRUCTIONS
        )
        
        # Log the formatted history for debugging
        logger.info(f"Tool call iteration {tool_call_count + 1}")
        # logger.info("Formatted history: %s", formatted_history)
        
        try:
            # Call Gemma
            response = model.generate_content(
                formatted_history,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=768,
                ),
                safety_settings={
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_ONLY_HIGH",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
                }
            )
            
            # Clean up the response text
            assistant_response = clean_response_text(response.text)
            
            # Check for function call
            function_call = extract_function_call(assistant_response)
            
            if function_call:
                # Extract function call details
                function_name = function_call.get("name")
                parameters = function_call.get("parameters", {})
                
                logger.info(f"Detected function call: {function_name}")
                logger.info(f"Parameters: {parameters}")
                
                # Check if the function is valid
                if function_name in tools.tool_map:
                    # Round time parameter to nearest hour if present
                    if "time" in parameters:
                        time_param = parameters["time"]
                        rounded_time = utils.round_time_to_nearest_hour(time_param)
                        if rounded_time:
                            parameters["time"] = rounded_time
                    
                    # Call the appropriate tool function
                    try:
                        tool_function = tools.tool_map[function_name]
                        tool_result = tool_function(**parameters)
                        
                        # Add tool call to LLM conversation history
                        st.session_state.llm_messages.append({
                            "role": "assistant", 
                            "content": assistant_response
                        })
                        
                        # Add tool result to LLM conversation history
                        st.session_state.llm_messages.append({
                            "role": "user", 
                            "content": f"Function result: {tool_result}"
                        })
                        
                        # Increment tool call count
                        tool_call_count += 1
                        
                        # Continue the loop
                        continue
                        
                    except Exception as e:
                        # Handle tool call error
                        logger.error(f"Error calling tool {function_name}: {str(e)}")
                        
                        # Add error message to LLM conversation history
                        st.session_state.llm_messages.append({
                            "role": "assistant", 
                            "content": assistant_response
                        })
                        
                        st.session_state.llm_messages.append({
                            "role": "user", 
                            "content": f"Error calling function: {str(e)}"
                        })
                        
                        # Increment tool call count
                        tool_call_count += 1
                        
                        # Continue the loop
                        continue
                        
                else:
                    # Invalid function name
                    logger.error(f"Invalid function name: {function_name}")
                    
                    # Add error message to LLM conversation history
                    st.session_state.llm_messages.append({
                        "role": "assistant", 
                        "content": assistant_response
                    })
                    
                    st.session_state.llm_messages.append({
                        "role": "user", 
                        "content": f"Invalid function name: {function_name}"
                    })
                    
                    # Break the loop with the current response
                    final_assistant_response = assistant_response
                    break
                    
            else:
                # No function call detected - regular response
                final_assistant_response = assistant_response
                # Add response to LLM messages
                st.session_state.llm_messages.append({
                    "role": "assistant", 
                    "content": assistant_response
                })
                # Break the loop
                break
                
        except Exception as e:
            # Handle Gemma API error
            error_msg = f"Error generating response: {str(e)}"
            logger.error(f"Error calling Gemma API: {str(e)}")
            final_assistant_response = error_msg
            break
    
    # Display the final assistant response
    with st.chat_message("assistant"):
        st.write(final_assistant_response)
    
    # Add final response to chat history for display
    st.session_state.messages.append({
        "role": "assistant", 
        "content": final_assistant_response
    })
    
    # Rerun the app to update the chat history display
    st.rerun()
