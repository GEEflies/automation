#!/usr/bin/env python3
"""
NoteWall UGC Reaction Video Generator
======================================
Combines daily UGC reaction clips + app demos + AI-generated hooks
into 3 ready-to-post TikTok/Instagram Reels.

Video Structure:
  [0-2s]  Hook text overlay (full screen, bold)
  [2-5s]  UGC reaction video (scared/joyful/shocked)
  [5-15s] App demo footage showing NoteWall features
  [15-17s] CTA text ("Try NoteWall 👆")

Usage:
  1. Record 3 reaction videos and save to ugc_daily/YYYY-MM-DD/
  2. Add app demo clips to app_demos/
  3. Set your GEMINI_API_KEY below (or as env var)
  4. Run: python video_generator.py

Dependencies:
  pip install moviepy pillow google-genai
"""

import os
import sys
import json
import random
import textwrap
from datetime import datetime
from pathlib import Path

try:
    from moviepy import (
        VideoFileClip, ImageClip, CompositeVideoClip,
        concatenate_videoclips, ColorClip, TextClip
    )
except ImportError:
    try:
        from moviepy.editor import (
            VideoFileClip, ImageClip, CompositeVideoClip,
            concatenate_videoclips, ColorClip, TextClip
        )
    except ImportError:
        print("❌ moviepy not installed. Run: pip install moviepy")
        sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("❌ Pillow not installed. Run: pip install pillow")
    sys.exit(1)

try:
    from google import genai
except ImportError:
    try:
        import google.generativeai as genai
    except ImportError:
        print("❌ google-genai not installed. Run: pip install google-genai")
        sys.exit(1)

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

# Set your Gemini API key here or use the GEMINI_API_KEY env var
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# Model to use for hook generation (text model — fast and cheap)
GEMINI_MODEL = "gemini-3-pro-preview"

# Folder paths (relative to this script's directory)
SCRIPT_DIR = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
UGC_FOLDER = SCRIPT_DIR / "ugc_daily" / TODAY
DEMO_FOLDER = SCRIPT_DIR / "app_demos"
OUTPUT_FOLDER = SCRIPT_DIR / "output" / TODAY

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# Timing (seconds)
HOOK_DURATION = 2.5
CTA_DURATION = 2.5
MAX_DEMO_DURATION = 10  # Trim demo clips to this max

# Styling
BG_COLOR = (15, 15, 19)        # Dark background
HOOK_TEXT_COLOR = (255, 255, 255)
CTA_TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (167, 139, 250)  # Purple accent

# Reaction types to process
REACTIONS = ["scared", "joyful", "shocked"]

# Emotion Mapping for Reactions
# Maps the video reaction filename/type to the hook emotion tags
REACTION_TO_EMOTION = {
    "scared": ["Urgent", "Shocked", "Frustrated"],
    "joyful": ["Life Hack", "Shocked"],
    "shocked": ["Shocked", "Skeptical", "Urgent"],
    "confused": ["Skeptical", "Frustrated", "Shocked"],
    "satisfied": ["Life Hack", "Frustrated"] 
}

# Global genai client reference
_genai_client = None

# ═══════════════════════════════════════════════════════
# PROVEN HOOKS DATABASE (from Social Growth Engineers)
# ═══════════════════════════════════════════════════════
HOOKS_DB = []

def load_hooks_db():
    """Load hooks from top_hooks.json if available, otherwise use defaults."""
    global HOOKS_DB
    json_path = SCRIPT_DIR / "top_hooks.json"
    
    defaults = [
        {"text": "POV: you stop forgetting everything because it's on your lock screen", "emotion": "Joyful"},
        {"text": "Wait... you can put NOTES on your WALLPAPER?? 😱", "emotion": "Shocked"},
        {"text": "Why is nobody talking about putting your to-do list on your wallpaper", "emotion": "Curious"},
        {"text": "If you struggle with forgetting things, you NEED to see this", "emotion": "Fear"},
        {"text": "POV: your lock screen actually makes you productive now", "emotion": "Joyful"},
        {"text": "widgets are so 2023... this is what you ACTUALLY need", "emotion": "Curious"},
        {"text": "my lock screen does more than any to-do app I've tried", "emotion": "Shocked"},
        {"text": "stop ignoring your reminders. make them IMPOSSIBLE to ignore.", "emotion": "Fear"}
    ]
    
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                loaded_hooks = json.load(f)
                if isinstance(loaded_hooks, list) and len(loaded_hooks) > 0:
                    # Normalize to object format if it's a list of strings (backward compatibility)
                    normalized = []
                    for h in loaded_hooks:
                        if isinstance(h, str):
                            normalized.append({"text": h, "emotion": "General"})
                        elif isinstance(h, dict):
                            normalized.append(h)
                    HOOKS_DB = normalized
                    print(f"📚 Loaded {len(HOOKS_DB)} hooks from top_hooks.json")
                    return
        except Exception as e:
            print(f"⚠️  Error loading top_hooks.json: {e}")
    
    HOOKS_DB = defaults
    print(f"📚 using {len(HOOKS_DB)} default hooks")

# Load hooks immediately
load_hooks_db()

# ═══════════════════════════════════════════════════════
# GEMINI HOOK GENERATION
# ═══════════════════════════════════════════════════════

def setup_gemini():
    """Configure the Gemini API."""
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("⚠️  No Gemini API key set. Using fallback hooks from database.")
        return False
    # New google-genai package uses a client
    global _genai_client
    _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return True


def generate_hooks_via_gemini(count=3):
    """Generate viral hooks using Gemini API."""
    prompt = f"""Generate {count} viral hooks (3-8 words each) for TikTok/Instagram Reels about NoteWall.

NOTEWALL: A productivity app that turns your phone's lock screen into a dynamic canvas for notes, goals, reminders, habits, quotes, and to-do lists. Notes are "burned" directly onto the wallpaper — NOT widgets, NOT notifications. You see them 150+ times a day every time you glance at your phone. Works on iPhone and Android.

TARGET AUDIENCE: Women aged 25-45 who struggle with mental load, mom brain, forgetting tasks, anxiety about missing important things. Busy moms, professionals, forgetful people who've tried every productivity app.

EMOTIONAL ANGLE: The relief of not forgetting things anymore. The simplicity of seeing your to-do list without opening any app. The hack that actually works.

Each hook must:
- Be 3-8 words max (short = better engagement)
- Create curiosity or urgency about putting notes on your LOCK SCREEN WALLPAPER
- NOT mention the app name "NoteWall" (that comes later in the CTA)
- Focus on the UNIQUE angle: wallpaper notes, not widgets, not another reminder app
- Use one of these proven viral formats:
  * "POV: When you..." (seeing notes on lock screen for first time)
  * "This changed everything..." (discovering wallpaper productivity)
  * "Why didn't I know..." (shock/discovery angle)
  * "If you forget things..." (calling out the pain point)
  * "Wait... your wallpaper can WHAT?" (pattern interrupt)
  * "Stop using [widgets/reminders]..." (positioning against old solutions)
  * "The mental load hack that..." (empathetic, supportive)

Return ONLY the hooks, one per line, no numbering, no quotes, no extra text."""

    try:
        response = _genai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        text = response.text.strip()
        hooks = [line.strip().strip('"').strip("'") for line in text.split('\n') if line.strip()]
        # Filter to reasonable length
        hooks = [h for h in hooks if 3 <= len(h.split()) <= 10 and len(h) < 60]
        return hooks[:count] if len(hooks) >= count else hooks + random.sample(HOOKS_DB, count - len(hooks))
    except Exception as e:
        print(f"⚠️  Gemini API error: {e}")
        print("   Falling back to hook database.")
        return random.sample(HOOKS_DB, min(count, len(HOOKS_DB)))


def get_hooks_for_reactions(reactions):
    """Get hooks from the local database that match the requested reaction emotions."""
    start_hooks = []
    
    # Track used indices to avoid duplicates if possible
    used_text = set()
    
    for r in reactions:
        # Get target emotions for this reaction (e.g. "scared" -> ["Fear", "Shocked"])
        target_emotions = REACTION_TO_EMOTION.get(r.lower(), [])
        
        # Filter DB for matching hooks
        # We look for hooks where the emotion matches OR hooks that are 'General' if no match found
        candidates = [h for h in HOOKS_DB if h.get("emotion") in target_emotions]
        
        # If no specific match, try finding anything not used
        if not candidates:
            candidates = [h for h in HOOKS_DB if h.get("text") not in used_text]
            
        if not candidates:
             candidates = HOOKS_DB # Absolute fallback
             
        # Pick one
        choice = random.choice(candidates)
        used_text.add(choice["text"])
        start_hooks.append(choice["text"])

    return start_hooks


# ═══════════════════════════════════════════════════════
# TEXT OVERLAY CREATION
# ═══════════════════════════════════════════════════════

def find_font():
    """Find a suitable bold font on the system."""
    font_paths = [
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFNSDisplayCondensed-Bold.otf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        # Windows
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return fp
    return None


def create_text_overlay(text, duration, bg_color=BG_COLOR, text_color=HOOK_TEXT_COLOR,
                        font_size=80, subtitle=None):
    """Create a text overlay video clip with centered bold text."""
    img = Image.new('RGB', (VIDEO_WIDTH, VIDEO_HEIGHT), color=bg_color)
    draw = ImageDraw.Draw(img)

    font_path = find_font()
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        small_font = ImageFont.truetype(font_path, int(font_size * 0.5)) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Word wrap the text
    max_chars = max(12, int(VIDEO_WIDTH / (font_size * 0.55)))
    wrapped = textwrap.fill(text, width=max_chars)

    # Calculate text position (center)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (VIDEO_WIDTH - text_width) // 2
    y = (VIDEO_HEIGHT - text_height) // 2 - 40

    # Draw subtle accent line above text
    line_y = y - 30
    line_width = min(text_width, 200)
    draw.line([(VIDEO_WIDTH - line_width) // 2, line_y,
               (VIDEO_WIDTH + line_width) // 2, line_y],
              fill=ACCENT_COLOR, width=4)

    # Draw main text
    draw.multiline_text((x, y), wrapped, fill=text_color, font=font, align='center')

    # Draw subtitle if provided
    if subtitle:
        sub_bbox = draw.textbbox((0, 0), subtitle, font=small_font)
        sub_width = sub_bbox[2] - sub_bbox[0]
        sub_x = (VIDEO_WIDTH - sub_width) // 2
        sub_y = y + text_height + 40
        draw.text((sub_x, sub_y), subtitle, fill=(*ACCENT_COLOR, 200), font=small_font)

    # Save temp image and create clip
    temp_path = str(OUTPUT_FOLDER / '_temp_overlay.png')
    img.save(temp_path)
    clip = ImageClip(temp_path).set_duration(duration).resize((VIDEO_WIDTH, VIDEO_HEIGHT))

    return clip


# ═══════════════════════════════════════════════════════
# VIDEO PROCESSING
# ═══════════════════════════════════════════════════════

def resize_clip(clip, target_w=VIDEO_WIDTH, target_h=VIDEO_HEIGHT):
    """Resize a video clip to fit the target dimensions (crop to fill)."""
    # Calculate scaling to fill the frame
    scale_w = target_w / clip.w
    scale_h = target_h / clip.h
    scale = max(scale_w, scale_h)

    resized = clip.resize(scale)

    # Center crop
    x_center = resized.w / 2
    y_center = resized.h / 2
    cropped = resized.crop(
        x1=x_center - target_w / 2,
        y1=y_center - target_h / 2,
        x2=x_center + target_w / 2,
        y2=y_center + target_h / 2
    )

    return cropped


def process_ugc_clip(filepath):
    """Load and process a UGC reaction clip."""
    clip = VideoFileClip(str(filepath))
    clip = resize_clip(clip)
    return clip


def get_random_demo():
    """Get a random app demo clip."""
    demo_files = [
        f for f in DEMO_FOLDER.iterdir()
        if f.suffix.lower() in ('.mp4', '.mov', '.avi', '.mkv', '.webm')
    ]
    if not demo_files:
        return None
    demo_path = random.choice(demo_files)
    clip = VideoFileClip(str(demo_path))

    # Trim to max duration
    if clip.duration > MAX_DEMO_DURATION:
        clip = clip.subclip(0, MAX_DEMO_DURATION)

    clip = resize_clip(clip)
    return clip


def create_video(reaction_type, hook_text, video_num):
    """Create a single combined video."""
    print(f"\n{'='*50}")
    print(f"📹 Creating Video {video_num} ({reaction_type} reaction)")
    print(f"   Hook: \"{hook_text}\"")
    print(f"{'='*50}")

    clips_to_close = []

    try:
        # 1. Create hook overlay (0 - 2.5s)
        print("   ⏳ Creating hook overlay...")
        hook_clip = create_text_overlay(
            hook_text,
            duration=HOOK_DURATION,
            font_size=80
        )
        clips_to_close.append(hook_clip)

        # 2. Load UGC reaction video
        ugc_path = UGC_FOLDER / f"ugc_{reaction_type}.mp4"
        if not ugc_path.exists():
            # Try without extension-specific check
            for ext in ['.mp4', '.mov', '.MOV', '.MP4']:
                alt_path = UGC_FOLDER / f"ugc_{reaction_type}{ext}"
                if alt_path.exists():
                    ugc_path = alt_path
                    break

        if not ugc_path.exists():
            print(f"   ⚠️  UGC file not found: {ugc_path}")
            print(f"       Creating placeholder clip instead.")
            ugc_clip = create_text_overlay(
                f"[{reaction_type.upper()} REACTION]",
                duration=3,
                bg_color=(30, 20, 40),
                font_size=60,
                subtitle="Replace with your recorded reaction"
            )
        else:
            print(f"   ⏳ Loading UGC clip: {ugc_path.name}")
            ugc_clip = process_ugc_clip(ugc_path)
        clips_to_close.append(ugc_clip)

        # 3. Load app demo
        print("   ⏳ Loading app demo clip...")
        demo_clip = get_random_demo()
        if demo_clip is None:
            print("   ⚠️  No app demos found in app_demos/")
            print("       Creating placeholder clip.")
            demo_clip = create_text_overlay(
                "NoteWall App Demo",
                duration=MAX_DEMO_DURATION,
                bg_color=(20, 15, 35),
                font_size=60,
                subtitle="Add your app demo clips to app_demos/"
            )
        clips_to_close.append(demo_clip)

        # 4. Create CTA overlay (15 - 17s)
        print("   ⏳ Creating CTA overlay...")
        cta_texts = [
            ("NoteWall 👆", "Lock Screen Notes — App Store & Google Play"),
            ("Search NoteWall", "Your lock screen, your to-do list ✨"),
            ("NoteWall", "Notes on your wallpaper — link in bio"),
        ]
        cta_text, cta_sub = random.choice(cta_texts)
        cta_clip = create_text_overlay(
            cta_text,
            duration=CTA_DURATION,
            font_size=90,
            subtitle=cta_sub
        )
        clips_to_close.append(cta_clip)

        # 5. Concatenate all clips
        print("   ⏳ Combining clips...")
        final = concatenate_videoclips([
            hook_clip,
            ugc_clip,
            demo_clip,
            cta_clip
        ], method="compose")

        # 6. Export
        output_path = OUTPUT_FOLDER / f"video_{video_num}_{reaction_type}.mp4"
        print(f"   ⏳ Exporting to: {output_path}")

        final.write_videofile(
            str(output_path),
            fps=FPS,
            codec='libx264',
            audio_codec='aac',
            preset='medium',
            bitrate='5000k',
            logger='bar'
        )

        print(f"   ✅ Video {video_num} saved: {output_path}")
        return str(output_path)

    except Exception as e:
        print(f"   ❌ Error creating video {video_num}: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        # Clean up clips
        for clip in clips_to_close:
            try:
                clip.close()
            except:
                pass
        # Clean up temp files
        temp_path = OUTPUT_FOLDER / '_temp_overlay.png'
        if temp_path.exists():
            temp_path.unlink()


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════════════════╗
║       🎯 NoteWall UGC Video Generator               ║
║       Generating 3 reaction videos for today         ║
╚══════════════════════════════════════════════════════╝
    """)
    print(f"📅 Date: {TODAY}")
    print(f"📁 UGC folder: {UGC_FOLDER}")
    print(f"📁 Demo folder: {DEMO_FOLDER}")
    print(f"📁 Output folder: {OUTPUT_FOLDER}")

    # Create output directory
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    # Check UGC folder
    if not UGC_FOLDER.exists():
        print(f"\n⚠️  UGC folder not found: {UGC_FOLDER}")
        print(f"   Creating it now... Please add your reaction videos:")
        UGC_FOLDER.mkdir(parents=True, exist_ok=True)
        for r in REACTIONS:
            print(f"   - ugc_{r}.mp4")
        print(f"\n   Videos will use placeholders for missing clips.\n")

    # Check demo folder
    demo_count = 0
    if DEMO_FOLDER.exists():
        demo_count = len([f for f in DEMO_FOLDER.iterdir()
                         if f.suffix.lower() in ('.mp4', '.mov', '.avi', '.mkv', '.webm')])
    print(f"📊 Found {demo_count} app demo clip(s)")

    # Check for UGC files
    for r in REACTIONS:
        ugc_file = UGC_FOLDER / f"ugc_{r}.mp4"
        status = "✅" if ugc_file.exists() else "⚠️  missing"
        print(f"   ugc_{r}.mp4: {status}")

    # Generate hooks
    print(f"\n🪝 Matching hooks to reactions...")
    
    # We prefer the curated viral database now that is populated
    if len(HOOKS_DB) > 0:
        print(f"   Using curated viral library ({len(HOOKS_DB)} hooks)")
        hooks = get_hooks_for_reactions(REACTIONS)
    else:
        use_gemini = setup_gemini()
        if use_gemini:
            hooks = generate_hooks_via_gemini(len(REACTIONS))
            print(f"   Generated {len(hooks)} hooks via Gemini API")
        else:
            # Should not happen if defaults are loaded
            hooks = ["Check out NoteWall!"] * len(REACTIONS)

    for i, hook in enumerate(hooks):
        print(f"   Hook {i+1} ({REACTIONS[i]}): \"{hook}\"")

    # Generate videos
    print(f"\n🎬 Starting video generation...\n")
    results = []

    for i, reaction in enumerate(REACTIONS):
        hook = hooks[i]
        result = create_video(reaction, hook, i + 1)
        results.append(result)

    # Summary
    print(f"\n{'='*50}")
    print(f"📊 GENERATION SUMMARY")
    print(f"{'='*50}")
    successful = [r for r in results if r]
    failed = len(results) - len(successful)
    print(f"✅ Successful: {len(successful)}")
    if failed:
        print(f"❌ Failed: {failed}")
    for r in successful:
        print(f"   📹 {r}")
    print(f"\n🎉 Done! Find your videos in: {OUTPUT_FOLDER}")


if __name__ == "__main__":
    main()
