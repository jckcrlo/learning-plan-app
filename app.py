import os
import google.generativeai as genai
from flask import Flask, request, jsonify
import io
import traceback # For better error logging
import json # <-- We need this new library

# --- Configuration ---
# PASTE YOUR API KEY HERE:
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Configure the Gemini client
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest') # The model we know works!

# Create the Flask app
app = Flask(__name__, static_folder='static', static_url_path='')

def create_lesson_prompt(topic, knowledge, skill):
    """
    This is the new, much more reliable JSON-based prompt.
    It now contains ALL of your detailed, UNCHANGED instructions.
    """
    return f"""
    You are an expert curriculum designer for a Grade 10 TLE (Cookery) teacher at St. Mary's Academy, a private Catholic school.
    Your task is to generate 14 lesson plan components based on the user's provided Topic, Knowledge, and Skill.
    
    PROVIDED BY USER:
    Topic: "{topic}"
    Knowledge (PoC): "{knowledge}"
    Skill (PoC): "{skill}"

    IMPORTANT: Your response MUST be a single, valid JSON object. Do not add any text or formatting before or after the JSON.
    You can use newlines (\\n) inside the JSON values (like for vocabulary).

    Please fill in the values for the following 14 keys, following the instructions for each key:
    {{
      "rvw": "(Review: One short 'How...' question that recalls the previous lesson topic based from the previous day topic.)",
      "fcs": "(Focus: One concise or very extremely brief words that states the primary learning topic of this lesson.)",
      "vcb": "(Vocabularies: Five bulleted technical or unfamiliar terms (each begins with '• ') with one-line student-friendly definitions. Each bulleted word must be on its own line, e.g., '• Term 1: ...\\n• Term 2: ...')",
      "mtv": "(Motivation: A short attention-getting opener (title then 1-2 sentence description) that connects to students' experience. Example: 'Poultry Hunt – Students look at pictures of different poultry types...')",
      "apk": "(Activating Prior Knowledge: One 'How...' question that connects students' prior learning/experience to the present topic (not about the main topic itself).)",
      "activities": "(Activities: A classroom-based activity. Format: '<b>Activities:</b> (Creative Title)\\nDirection: (Brief steps, resources, grouping, time cue, and expected product)')",
      "boc": "(Broadening of concepts: Exactly one 'How...' question that connects the lesson to wider contexts or applications, like their lives.)",
      
      "values": "(Core/Related Values: Choose one core value (Faith / Excellence / Service) and one related value. Write this line exactly: <b>Core/Related Values:</b> <u>[Core] / [Related]</u> then immediately write one reflective question in this exact style: How does [related value] demonstrate [core value] in the context of [topic]? (Reference list: 1. Faith: Strong faith in God; Prophetic witness to Gospel values; Nationalism; Justice; Communion. 2. Excellence: Integrity; Competence; Resourcefulness; Discipline; Self-reliance. 3. Service: Stewardship; Humility; Charity; Courage; Preferential love for the poor))",
      
      "social": "(Social Orientation: Start with the social issue title (e.g., Food Waste Reduction, Public Health) as: <b>Social Orientation:</b> <u>[Issue]</u> then write one focused reflective question: How can learning [topic] contribute to [social issue outcome] in the community?)",
      "discipline": "(Lesson Across Discipline: Present two subjects first (format: <b>Lesson Across Discipline:</b> <u>[Subject 1] and [Subject 2]</u>) and write the linking question: How do [Subject 1] principles in [topic] align with [Subject 2] skills and topic in this lesson?)",
      "biblical": "(Biblical Integration: Start the line exactly with <b>Biblical Integration:</b> followed by the full Bible verse (book name, chapter, verse). Use this format: <b>Biblical Integration:</b> <u>Bible Verse - \"The content of the bible verse\"</u>)",
      "eva": "(Evaluation: A short, pen-and-paper practical assessment task (e.g., Short quiz, essay, identification, classification) that measures the Knowledge.)",
      "smr_act": "(Summary and Action: A single brief 'How...' question that summarizes the main point, AND a second 'How...' question asking students how they will apply the learning in daily life.)",
      "pua": "(Purposive Assignment: A unique, non-repetitive take-home task that can be done at home. Describe expected output, length, medium, and due date placeholder.)"
    }}
    """

def parse_ai_response(text, knowledge, skill):
    """
    This function now parses the AI's JSON response.
    It's much safer and more reliable.
    """
    
    # AI sometimes wraps its JSON in ```json ... ```. We must remove this.
    if text.strip().startswith("```json"):
        text = text.strip()[7:] # Remove "```json"
    if text.strip().endswith("```"):
        text = text.strip()[:-3] # Remove "```"
        
    try:
        # Load the text as a JSON object
        data = json.loads(text)
    except Exception as e:
        print(f"JSON PARSE ERROR: {e}")
        print(f"FAILED TO PARSE THIS TEXT: {text}")
        # If JSON fails, return an error for all fields
        data = { "error": f"AI Response Error: {e}" }

    # Safely get each piece of content.
    # .get("key", "default") returns "default" if the key is missing.
    # This PREVENTS crashes and mis-aligned columns.
    return {
        "rvw": data.get("rvw", "(AI Error)"),
        "fcs": data.get("fcs", "(AI Error)"),
        "vcb": data.get("vcb", "(AI Error)"),
        "mtv": data.get("mtv", "(AI Error)"),
        "apk": data.get("apk", "(AI Error)"),
        "knowledge": knowledge, # From user
        "skill": skill,       # From user
        "activities": data.get("activities", "(AI Error)"),
        "boc": data.get("boc", "(AI Error)"),
        "values": data.get("values", "(AI Error)"),
        "social": data.get("social", "(AI Error)"),
        "discipline": data.get("discipline", "(AI Error)"),
        "biblical": data.get("biblical", "(AI Error)"),
        "eva": data.get("eva", "(AI Error)"),
        "smr_act": data.get("smr_act", "(AI Error)"),
        "pua": data.get("pua", "(AI Error)")
    }

def create_empty_content(knowledge="", skill=""):
    """
    Creates a blank 16-part dictionary for days the user left blank.
    (14 from AI + 2 from user)
    """
    return {
        "rvw": "", "fcs": "", "vcb": "", "mtv": "", "apk": "",
        "knowledge": knowledge, "skill": skill, "activities": "", 
        "boc": "", "values": "", "social": "", "discipline": "", "biblical": "", 
        "eva": "", "smr_act": "", "pua": ""
    }

# --- The Main API Route ---
@app.route('/generate-content', methods=['POST'])
def generate_content():
    try:
        data = request.json
        days_data = data.get('days') # This is the list of 4 day-objects
        
        all_results = []
        
        # Loop 4 times (once for each day's data)
        for day in days_data:
            topic = day.get('topic')
            knowledge = day.get('knowledge')
            skill = day.get('skill')
            
            # If any field is blank, skip the AI call and add empty content
            if not topic or not knowledge or not skill:
                all_results.append(create_empty_content(knowledge, skill))
                continue
            
            try:
                # 1. Create the specific prompt
                full_prompt = create_lesson_prompt(topic, knowledge, skill)
                
                # 2. Call the Gemini API
                response = model.generate_content(full_prompt)
                
                # 3. Parse the response and add it to our list
                parsed_content = parse_ai_response(response.text, knowledge, skill)
                all_results.append(parsed_content)
                
            except Exception as e:
                print(f"Error processing day with topic {topic}: {e}", flush=True)
                all_results.append(create_empty_content(knowledge, skill)) # Add empty on fail
        
        # 4. Send all 4 results back to the website
        return jsonify({"results": all_results})

    except Exception as e:
        # This is the main error catcher
        print("---!!! A MAJOR CRASH OCCURRED !!!---", flush=True)
        print(traceback.format_exc(), flush=True) # This prints the full error
        return jsonify({"error": str(e)}), 500

# --- Route to serve your website (index.html) ---
@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    app.run(debug=True)