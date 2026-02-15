import os
import openpyxl
import json
import random
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

# Initialize Gemini client
client = genai.Client(api_key=api_key)

# Excel File Path
excel_file = "[Social Growth Engineers] Education & Productivity Hooks Dataset.xlsx"

try:
    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    
    # Column Indices (0-based) based on previous analysis
    # ('Username', 'Video URL', 'Hook', 'Caption', 'Duration', 'Posted At', 'Views', 'Likes', 'Comments', ...)
    HOOK_COL = 2
    VIEWS_COL = 6
    
    # Start reading data
    DATA_START_ROW = 4
    
    candidates = []
    
    print(f"Reading and analyzing viral hooks from {excel_file}...")
    
    for row in ws.iter_rows(min_row=DATA_START_ROW, values_only=True):
        if not row or len(row) <= VIEWS_COL:
            continue
            
        hook_text = row[HOOK_COL]
        views = row[VIEWS_COL]
        
        # Validation
        if not hook_text or not isinstance(hook_text, str) or len(hook_text.strip()) < 10:
            continue
            
        # Clean views data (sometimes it might be a string or blank)
        # Try to parse views as float
        v = 0.0
        try:
            if isinstance(views, str):
                views = views.replace(',', '')
                if 'k' in views.lower():
                    v = float(views.lower().replace('k', '')) * 1000
                elif 'm' in views.lower():
                    v = float(views.lower().replace('m', '')) * 1000000
                else:
                    v = float(views)
            elif isinstance(views, (int, float)):
                v = float(views)
        except (ValueError, TypeError):
            v = 0.0
            
        candidates.append({
            "hook": hook_text.strip(),
            "views": v
        })
    
    print(f"Found {len(candidates)} total hooks.")

    # Sort by views (descending) to get the most viral ones
    candidates.sort(key=lambda x: x["views"], reverse=True)
    
    # Take top 30 most viral hooks
    # If not enough viral ones, take whatever we have
    top_candidates = candidates[:30] if len(candidates) >= 30 else candidates
    
    if not top_candidates:
        print("No valid hooks found! Using generic fallback.")
        top_candidates = [{"hook": "Generic hook about productivity"}]
    
    print(f"Selected top {len(top_candidates)} viral hooks based on view count.")
    # Show top 3 for debug
    for i, c in enumerate(top_candidates[:3]):
        print(f"#{i+1}: {c['views']} views - {c['hook']}")
    
    # Prepare the hooks for the prompt
    # Get top viral hooks to use as inspiration
    # We want a large library of 100 hooks, so we should provide significant inspiration
    top_1000 = candidates[:1000]
    random.shuffle(top_1000)
    
    # Send 150 diverse high-performing hooks as examples
    hooks_to_send = [c['hook'] for c in top_1000[:150]]
    hooks_str = "\n".join([f"- {h}" for h in hooks_to_send])
    
    prompt = f"""
    You are a viral content strategist for **NoteWall**, an iOS app that puts notes/to-do lists directly on your lock screen wallpaper.
    
    **The Goal:**
    Create a library of **100 VIRAL HOOKS** for UGC (User Generated Content) ads featuring a **MALE creator**.
    
    **Target Audience & Persona:**
    - **Persona:** Male, relatable, productivity-focused, direct, "bro-to-bro" advice.
    - **Tone:** Shocked, Frustrated, Urgent, Skeptical, High Energy.
    - **AVOID:** "Aesthetic", "Cozy", "Cute", "Satisfying", "Soft", "Pretty". Do NOT use words like "obsession", "literally dying", "so aesthetic". 
    
    **Categorization Task:**
    For each hook, you MUST assign one of the following 5 EMOTIONS that convert best for male-led productivity UGC:
    1. **Shocked** (Disbelief, "Wait, this exists?", "My life is a lie", "WTF")
    2. **Frustrated** (Relatable pain, "I'm so done with...", "Why is this so hard?", "Stop struggling")
    3. **Skeptical** (Cynical turned believer, "I thought this was fake", "Actually useful?", "No way")
    4. **Urgent** (FOMO, "You need this NOW", "Delete your notes app", "Do this immediately")
    5. **Life Hack** (Efficiency, "Cheat code", "Work smarter", "100x productivity")

    **Visual Context of the Video:**
    - **Shocked:** Eyes wide, pointing at screen, disbelief.
    - **Frustrated:** Face-palm, shaking head, "I can't believe I wasted time".
    - **Skeptical:** Eyebrow raised, looking at phone suspiciously, then nodding.
    - **Urgent:** Leaning close to camera, intense eye contact.
    - **Life Hack:** Smirk, confident nod, "come here" gesture.
    
    **Transformation Task:**
    I have provided 150 proven viral hooks from other productivity/student videos below.
    Use these as structural inspiration to create 100 UNIQUE hooks for NoteWall.
    
    **Requirements:**
    - **Quantity:** EXACTLY 100 hooks.
    - **Length:** Short and punchy (must be readable in 2 seconds).
    - **Tone:** Masculine, Authentic, "TikTok Native".
    - **Format:** JSON Array of OBJECTS.
    - **Context:** Must make sense with a "Reaction + App Demo" visual.
    
    **Inspiration Source (Viral Hooks):**
    {hooks_str}
    
    **Output:**
    Return ONLY a raw JSON array of objects.
    Example:
    [
      {{"text": "I was today years old finding THIS?! \ud83e\udd2f", "emotion": "Shocked"}},
      {{"text": "Stop using the default notes app! It's trash.", "emotion": "Frustrated"}},
      {{"text": "I thought this app was a scam... I was wrong.", "emotion": "Skeptical"}},
      {{"text": "If you have ADHD, download this NOW.", "emotion": "Urgent"}},
      {{"text": "This iPhone hack feels illegal.", "emotion": "Life Hack"}}
    ]
    (Strictly adhere to the 5 categories: Shocked, Frustrated, Skeptical, Urgent, Life Hack. NO Aesthetic hooks.)
    """

    print("Sending to Gemini for personalization...")
    
    # Use a supported model
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[prompt]
    )
    
    response_text = response.text
    
    # Clean up markdown
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()
        
    final_hooks = json.loads(response_text)
    
    # Post-process to ensure consistent keys and remove bad hashtags
    clean_hooks = []
    
    valid_emotions = ["Shocked", "Frustrated", "Skeptical", "Urgent", "Life Hack"]
    
    for item in final_hooks:
        if isinstance(item, str):
            # If AI messed up and returned strings, try to categorize simply
            text = item
            emotion = "Life Hack" # Default
            if "?" in text or "!" in text: emotion = "Shocked"
            clean_hooks.append({"text": text.replace("#NoteWall", "").strip(), "emotion": emotion})
        elif isinstance(item, dict):
            text = item.get("text", "")
            emotion = item.get("emotion", "Life Hack")
            
            # Normalization
            emotion = emotion.capitalize()
            if "Life" in emotion or "Hack" in emotion: emotion = "Life Hack" # Handle space naming issues
            
            if emotion not in valid_emotions:
                # Map close enough
                if "Relie" in emotion: emotion = "Life Hack" 
                elif "Urg" in emotion or "Fear" in emotion: emotion = "Urgent"
                elif "Mind" in emotion: emotion = "Shocked"
                elif "Anger" in emotion or "Hate" in emotion: emotion = "Frustrated"
                elif "Curious" in emotion: emotion = "Skeptical"
                else: emotion = "Life Hack"
                
            if text:
                clean_hooks.append({"text": text.replace("#NoteWall", "").strip(), "emotion": emotion})
                
    final_hooks = clean_hooks
    
    print(f"Generated {len(final_hooks)} personalized high-performance hooks.")
    
    # Save to top_hooks.json
    output_file = "top_hooks.json"
    with open(output_file, "w") as f:
        json.dump(final_hooks, f, indent=2)
        
    print(f"Successfully saved to {output_file}")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"An error occurred: {e}")
