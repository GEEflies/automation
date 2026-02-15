import subprocess
from flask import Flask, jsonify, request, send_from_directory, send_file, send_file
import os
import random
import json
import textwrap
import zipfile
import io
from pathlib import Path
# Removed moviepy import as we now use ffmpeg subprocess
# from moviepy import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# Config
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'generated_shorts'
HOOKS_FILE = 'top_hooks.json'
USED_HOOKS_FILE = 'used_hooks.json'

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Colors and styling
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
HOOK_TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (167, 139, 250)
BG_COLOR = (0, 0, 0)

def load_hooks():
    try:
        with open(HOOKS_FILE, 'r') as f:
            hooks = json.load(f)
            # Ensure format is consistently objects
            normalized = []
            for h in hooks:
                if isinstance(h, str):
                    normalized.append({"text": h, "emotion": "General"})
                elif isinstance(h, dict):
                    normalized.append(h)
            return normalized
    except Exception as e:
        print(f"Error loading hooks: {e}")
        return []

def load_used_hooks():
    try:
        if not os.path.exists(USED_HOOKS_FILE):
             return []
        with open(USED_HOOKS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading used hooks: {e}")
        return []

def mark_hook_as_used(hook):
    """Move hook from top_hooks.json to used_hooks.json"""
    try:
        # Load both
        all_hooks = load_hooks()
        used = load_used_hooks()
        
        # Remove from active
        # Use simple text matching
        updated_active = [h for h in all_hooks if h['text'] != hook['text']]
        
        # Add to used
        hook['used_at'] = str(os.urandom(4).hex()) # Simple timestamp placeholder or random ID
        used.insert(0, hook)
        
        # Save both
        with open(HOOKS_FILE, 'w') as f:
            json.dump(updated_active, f, indent=2)
            
        with open(USED_HOOKS_FILE, 'w') as f:
            json.dump(used, f, indent=2)
            
    except Exception as e:
        print(f"Error marking hook as used: {e}")


def find_font():
    """Find a suitable bold font on the system."""
    font_paths = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/SFCompactRounded-Bold.otf" 
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return fp
    return None

def get_video_duration_and_size(filepath):
    """Use ffprobe to get video duration and dimensions."""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-select_streams', 'v:0', 
            '-show_entries', 'stream=width,height,duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Output format should be: width\nheight\nduration
        parts = result.stdout.strip().split('\n')
        if len(parts) >= 3:
            w = int(parts[0])
            h = int(parts[1])
            try:
                d = float(parts[2])
            except ValueError:
                 # sometimes duration is N/A in stream, try format
                 cmd2 = [
                    'ffprobe', 
                    '-v', 'error', 
                    '-show_entries', 'format=duration', 
                    '-of', 'default=noprint_wrappers=1:nokey=1', 
                    filepath
                 ]
                 res2 = subprocess.run(cmd2, capture_output=True, text=True)
                 d = float(res2.stdout.strip())
            return w, h, d
        return 1080, 1920, 60.0 # Fallback
    except Exception as e:
        print(f"Error getting video info: {e}")
        return 1080, 1920, 60.0

def create_text_overlay(text, duration, video_size):
    """Create a text overlay image."""
    width, height = video_size
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_path = find_font()
    font_size = 110 # Bigger font size
    
    font = ImageFont.load_default()
    try:
        if font_path:
            # Check if it's Helvetica or similar .ttc
            if font_path.endswith('.ttc'):
                 # Index 0 usually Regular, let's try to find Bold if possible or just use a larger size
                 # Actually HelveticaNeue.ttc index 1 is usually Bold.
                 try:
                    font = ImageFont.truetype(font_path, font_size, index=1)
                 except:
                    font = ImageFont.truetype(font_path, font_size, index=0)
            else:
                 font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        print(f"Font load error: {e}")
        font = ImageFont.load_default()

    # Word wrap
    max_chars = 30 # Wider text area (was 15)
    wrapped = textwrap.fill(text, width=max_chars)

    # Calculate text position
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align='center', stroke_width=4)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (width - text_width) // 2
    # Position higher: around 25% from top
    y = int(height * 0.25) - (text_height // 2)

    # Outline (Stroke)
    stroke_width = 5 
    
    # Draw Text with outline
    try:
        # Try generic Pillow 10+ colored emoji handling
        draw.multiline_text(
            (x, y), 
            wrapped, 
            fill="white", 
            font=font, 
            align='center', 
            stroke_width=stroke_width, 
            stroke_fill="black",
            embedded_color=True
        )
    except TypeError:
        # Fallback
        draw.multiline_text(
            (x, y), 
            wrapped, 
            fill="white", 
            font=font, 
            align='center', 
            stroke_width=stroke_width, 
            stroke_fill="black"
        )


    # Save temp unique
    temp_overlay_filename = f"overlay_{os.urandom(4).hex()}.png"
    temp_overlay = os.path.join(UPLOAD_FOLDER, temp_overlay_filename)
    img.save(temp_overlay)
    
    return temp_overlay

def generate_video_internal(filepath, emotion):
    """Core logic to generate video from file and emotion."""
    all_hooks = load_hooks()
    
    # Filter by emotion
    target_emotion = emotion.capitalize()
    
    # Handle emotion variations or fallback mapping
    # Actually the hooks file should be clean now, but just in case
    candidates = [h for h in all_hooks if h.get('emotion') == target_emotion]
    if not candidates:
        # Fallback to general or any if exact match fails
        # Try looking for "Life Hack" if "Life Hack" fails due to space/case
        candidates = all_hooks

    if not candidates:
        raise Exception("No hooks found in database")
        
    selected_hook = random.choice(candidates)
    hook_text = selected_hook['text']
    
    # Process Video
    # Get video details
    w, h, duration = get_video_duration_and_size(filepath)
    
    # Max duration 60s
    max_duration = min(duration, 60)
    
    # Overlay duration (Full Video)
    overlay_duration = max_duration

    # Create overlay image
    temp_overlay_path = create_text_overlay(hook_text, overlay_duration, (w, h))

    output_filename = f"hook_{target_emotion}_{os.urandom(4).hex()}.mp4"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    cmd = [
        'ffmpeg', '-y',
        '-i', filepath,
        '-loop', '1', '-i', temp_overlay_path, # Loop the overlay image
        '-filter_complex', f"[0:v]scale={w}:{h}[base];[base][1:v]overlay=0:0:shortest=1",
        '-t', str(max_duration),
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-an', # Remove audio
        output_path
    ]
    
    print(f"Running ffmpeg: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # Mark as used after successful generation
    mark_hook_as_used(selected_hook)

    try:
            # Cleanup
            os.remove(temp_overlay_path)
    except:
            pass
            
    return output_path, hook_text, output_filename

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/top_hooks.json')
def get_hooks_json():
    return send_file('top_hooks.json')

@app.route('/used_hooks.json')
def get_used_hooks_json():
    if not os.path.exists(USED_HOOKS_FILE):
        return jsonify([])
    return send_file(USED_HOOKS_FILE)

@app.route('/upload-video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No video file"}), 400
    
    file = request.files['video']
    emotion = request.form.get('emotion', 'General')
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    _, ext = os.path.splitext(file.filename)
    if not ext: ext = '.mp4'
        
    filename = f"upload_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        output_path, hook_text, filename = generate_video_internal(filepath, emotion)
        
        # Cleanup input
        if os.path.exists(filepath):
            os.remove(filepath)
        
        return jsonify({
            "status": "success",
            "video_url": f"/download/{filename}",
            "hook_text": hook_text,
            "emotion": emotion.capitalize()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/batch-upload', methods=['POST'])
def batch_upload():
    # Expect video1, video2, video3 and emotion1, emotion2, emotion3
    generated_files = []
    
    try:
        for i in range(1, 4):
            key_file = f"video{i}"
            key_emotion = f"emotion{i}"
            
            if key_file in request.files and request.files[key_file].filename != '':
                file = request.files[key_file]
                emotion = request.form.get(key_emotion, 'General')
                
                _, ext = os.path.splitext(file.filename)
                if not ext: ext = '.mp4'
                
                filename = f"batch_{i}_{os.urandom(4).hex()}{ext}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                
                try:
                    output_path, _, out_name = generate_video_internal(filepath, emotion)
                    generated_files.append((out_name, output_path))
                    
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"Error processing batch item {i}: {e}")
                    # Continue to next item even if one fails
        
        if not generated_files:
            return jsonify({"error": "No videos processed successfully"}), 500
            
        # Create ZIP
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, path in generated_files:
                zf.write(path, name)
                
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name='notewall_batch.zip'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

if __name__ == '__main__':
    print("Starting Flask server on port 8000...")
    app.run(port=8000, debug=True)
