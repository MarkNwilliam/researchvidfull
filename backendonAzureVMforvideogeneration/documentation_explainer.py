import requests
import json
import os
import re
import time
from flask import Flask, request, jsonify, send_from_directory
from configparser import ConfigParser
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core.prompts import PromptTemplate
from direct_video_generator import generate_video_from_json
from chat_with_paper import ChatWithPaper
from flask_cors import CORS

app = Flask(__name__)

CORS(app)

# Initialize ChatWithPaper
paper_analyzer = ChatWithPaper()

# Constants
MEDIA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media')
VIDEO_DIR = os.path.join(MEDIA_ROOT, 'videos', '1080p60')

def clear_manim_cache(output_name):
    """Clear cache for the current output_name"""
    files_to_remove = [
        os.path.join(VIDEO_DIR, f"{output_name}.mp4"),
        os.path.join(VIDEO_DIR, f"{output_name}.log"),
        os.path.join(VIDEO_DIR, 'partial_movie_files', output_name)
    ]
    
    for path in files_to_remove:
        if os.path.exists(path):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path)
                print(f"Removed: {path}")
            except Exception as e:
                print(f"Error removing {path}: {e}")

def clean_generated_text(generated_text):
    """Extract and clean the JSON part from the generated text."""
    try:
        # Extract JSON content
        match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        if not match:
            raise ValueError("No valid JSON found in the generated text")

        json_text = match.group(0)

        # Fix invalid escape sequences by replacing single backslashes with double backslashes
        json_text = json_text.replace("\\", "\\\\")
        
        # Remove unnecessary newlines and tabs
        json_text = json_text.replace("\n", " ").replace("\t", " ").strip()

        # Parse the cleaned JSON
        return json.loads(json_text)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to extract or parse JSON: {e}")

def generate_video_json_with_ai(topic, pdf_url=None, paper_title=None, user_description=None):
    """Generate video JSON configuration using Azure OpenAI with LlamaIndex"""
    print(f"\nGenerating video JSON for topic: {topic}")

    # Get paper context if PDF is provided
       # Get paper context if PDF is provided
        # Get paper context if PDF is provided
    paper_context = ""
    custom_instructions = ""
    
    if pdf_url and paper_title:
        try:
            print(f"Analyzing paper: {paper_title} from {pdf_url}")
            # Get a summary of the paper to use as context
            paper_response = paper_analyzer.chat_with_paper(
                pdf_url=pdf_url,
                title=paper_title,
                question=f"Provide a comprehensive summary of the key points in this paper about {topic}"
            )
            if "answer" in paper_response:
                paper_context = f"""
=== IMPORTANT PAPER CONTEXT ===
The video should be based on this research paper titled "{paper_title}".
Key points from the paper:
{paper_response['answer']}
"""
        except Exception as e:
            print(f"Warning: Failed to analyze paper: {str(e)}")

    # Add user description if provided
    if user_description:
        custom_instructions = f"""
=== USER CUSTOM INSTRUCTIONS ===
The user provided these specific requirements:
{user_description}

SPECIAL INSTRUCTIONS:
1. Prioritize these custom requirements above all else
2. Incorporate all specified elements from the user
3. Adjust technical depth according to user's description
4. Focus on the aspects the user emphasized
"""
    
    llm = AzureOpenAI(
        model="gpt-4-32k",
        deployment_name="gpt-4-32k",
        api_key="3JgoLqcaXs1o03y22tvDOcJk19RbM1TiNCHaFjurnv3ejl8mKCgSJQQJ99BCACfhMk5XJ3w3AAAAACOGzuKe",
        azure_endpoint="https://nkugw-m8lhg8dl-swedencentral.openai.azure.com/",
        api_version="2024-05-01-preview"
    )

    prompt_template = PromptTemplate(
        template="""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
    You are an advanced AI assistant creating a technical video script about {topic}.
{paper_context}
{custom_instructions}
    The response **must** be **only JSON**, without any explanations, notes, or additional text.
Ensure:
- Use only the types i that structure and no other we only have code and title. 
- The text fields marked Pango Markup in the json example should be in Pango Markup format. 
- All newlines in code are escaped (`\\n`) in no situation should you not put those symbols by leaving space use those string symbols to leave spaces if code scene is added
- The JSON is fully valid and structured as follows:
- For symbols and math use Latex symbols ONLY and anothing else

**Use LaTeX Math Symbols**: 
   - Use `\\` for backslashes in LaTeX commands.
   - All mathematical symbols, variables, and equations must use LaTeX syntax.
   - Wrap all LaTeX math content in `$...$` for inline math or `\[...\]` for display math.
   - For example:
     - `ε` → `$\\epsilon$`
     - `α` → `$\\alpha$`
     - `E = mc^2` → `$E = mc^2$`

Generate a structured JSON for a technical video explanation about {topic}.

Supported Scene Types:
1. Title Scene (REQUIRED)
   - Introduces the topic with:
     * Engaging main title
     * Informative subtitle
     * Concise voiceover
     * Appropriate display duration

2. Overview Scene (OPTIONAL BUT RECOMMENDED)
   - Provides high-level context:
     * Descriptive text explaining core concepts
     * Optional subtitle for additional context
     * Voiceover narration
     * Configurable text creation time
     * Scene duration

3. Code Scene (OPTIONAL)
   - Demonstrates practical implementation:
     * Clear section title
     * Fully formatted code snippet
     * Strict code formatting rules:
       - 4 spaces for indentation
       - Escaped newlines (`\\n`)
       - Max 80 characters per line
       - Inline comments with two spaces
     * Introduction text and voiceover
     * Configurable code section highlights
     * Concluding remarks

4. Sequence Diagram Scene (OPTIONAL BUT RECOMMENDED)
   - Illustrates system interactions:
     * List of actors/participants
     * Sequence of interactions
     * Voiceover for each interaction
     * Optional title

5. Image+Text Scene (OPTIONAL BUT RECOMMENDED)
   - Title, text, voiceover
   - Wikipedia topic for images
   - Number of images and duration

6. Multi-Image+Text Scene (OPTIONAL BUT RECOMMENDED)
   - Title (optional), text, voiceover
   - Wikipedia topics for image search
   - Layout (horizontal/vertical), duration

7. Triangle Diagram Scene (OPTIONAL BUT RECOMMENDED)
   - Title (optional), voiceover
   - Top/left/right text boxes
   - Connection messages between boxes

8. Data Processing Flow (OPTIONAL BUT RECOMMENDED)
   - Blocks (input/processor/output)
   - Color-coded with voiceovers
   - Connecting arrows

9. Timeline Scene (OPTIONAL BUT RECOMMENDED)
    - Use the `timeline` scene type.
    - Include a `title` for the timeline.
    - Provide a list of `events`, where each event contains:
    - `year`: The year of the event.
    - `text`: A brief description of the event (This is only text not Pango Markup).
    - `event`: A brief description of the event (This is only text not Pango Markup).
    - `narration`: A detailed explanation of the event for the voiceover.

   CONTENT GUIDELINES:
1. Prioritize clarity over complexity
2. Use technical terms appropriately
3. Maintain consistent tone
4. Ensure logical flow between scenes
5. Balance visual and verbal content
6. Use formulas and equations in many explainations for simplicity

=== PANGO MARKDOWN FORMATTING GUIDE ===
Use these formatting tags in all text fields (main_text, subtitle, text, voiceover, etc.):

Basic Styling:
- **Bold text** → `<b>Bold text</b>`
- *Italic text* → `<i>Italic text</i>`
- Underlined text → `<u>Underlined text</u>`

Technical Formatting:
- `Code snippets` → `<tt>Code snippets</tt>`
- Variables → `<span foreground='#FF5555'>variable</span>`
- Important terms → `<span size='large'>Important</span>`

Lists and Structure:
- Bullet points:
<span foreground='#AAAAAA'>•</span> First item
<span foreground='#AAAAAA'>•</span> Second item

- Numbered lists:
<span foreground='#AAAAAA'>1.</span> First item
<span foreground='#AAAAAA'>2.</span> Second item

Colors:
- Use hex colors for highlights: `<span foreground='#34A853'>Success</span>`
- Consistent color scheme:
- Blue: `#4285F4` (for concepts)
- Green: `#34A853` (for success/positive)
- Red: `#EA4335` (for warnings/errors)
- Yellow: `#FBBC05` (for important notes)

JSON Structure Example:
```json
{
    "output_name": "TopicExplanationVideo",
    "scenes": [
        {
            "type": "title",
            "main_text": "Topic Title",
            "subtitle": "Detailed Explanation",
            "voiceover": "Introductory narrative",
            "duration": 5,
        },
        {
            "type": "overview",
            "text": "High-level concept explanation (In Pango Markup)",
            "voiceover": "Narrative overview",
            "creation_time": 10,
            "duration": 4,
            "subtitle": "Optional additional context (This is only text not Pango Markup)"
        },
                  {
            "type": "multi_image_text",
            "title": "string",
            "text": "string  (In Pango Markup)",
            "voiceover": "string (good depth explaination with rules of thumb and numbers statistics , real world examples etc)",
            "wikipedia_topics": ["string"] (used to search for images),
            "num_images": "number",
            "image_width": "optional_number",
            "layout": "horizontal|vertical",
            "duration": "number"
          },
        {
            "type": "code",
            "title": "Implementation Details",
            "code": "# Demonstration code\\n...",
            "intro": {
                "text": "Code context",
                "voiceover": "Code introduction narration"
            },
            "sections": [
                {
                    "title": "Key Code Section",
                    "highlight_start": 1,
                    "highlight_end": 3,
                    "voiceover": "Detailed code explanation",
                    "duration": 3
                }
            ],
            "conclusion": {
                "text": "Code summary",
                "voiceover": "Concluding code insights"
            }
        },
        {
            "type": "sequence",
            "title": "System Interaction Flow",
            "background": "optional_background.png",
            "actors": ["Actor1", "Actor2"],
            "interactions": [
                {
                    "from": "Actor1",
                    "to": "Actor2",
                    "type": "message",
                    "message": "Interaction description",
                    "voiceover": "Interaction explanation"
                }
            ]
        },
                {
            "type": "image_text",
            "title": "string",
            "text": "string  (In Pango Markup)",
            "voiceover": "string",
            "wikipedia_topic": "string (passed to api to search for images)",
            "num_images": 2,
            "duration": 6
        },
          {
            "type": "triangle",
            "title": "optional_string",
            "voiceover": "string (good depth explaination with rules of thumb and numbers statistics , real world examples etc)",
            "top_text": "string",
            "left_text": "string",
            "right_text": "string",
            "top_to_left": "optional_string",
            "top_to_right": "optional_string",
            "left_to_right": "optional_string",
            "right_to_left": "optional_string",
            "left_to_top": "optional_string",
            "right_to_top": "optional_string",
            "duration": "number"
          },
             {
        "type": "timeline",
        "title": "string",
        "events": [
          {
            "year": year (number for example 2000),
            "text": "string (plain text not pango markup)",
            "narration": "string.",
            "image_description": "string ( for lookup image in wikimedia api)"
          },
          {
            "year": year (number for example 2008),
            "text": "string (plain text not pango markup)",
            "narration": "string.",
            "image_description": "string ( for lookup image in wikimedia api)"
          },
          //More depending on the topic and what you thing is needed
        ],
      },
          {
            "type": "data_processing_flow",
            "blocks": [
              {
                "type": "input1|input2|processor|output",
                "text": "string",
                "voiceover": "string (good depth explaination with rules of thumb and numbers statistics , real world examples etc)",
                "color": "green|red|blue|purple"
              }
            ],
            "narration": {
              "conclusion": "string"
            }
          }
    ]
}
```
    Instructions:
    Always include a title scene to introduce the topic.
    Always make sure all voiceovers explain more than the text and give deeper explanations to complement the text and concepts, adding real-world examples, analogies, statistics, rules of thumb, etc.
    Only write pango markup where there is a a mark that its pango markup in the above josn example.
    Include an overview scene only if it adds value to the explanation (e.g., for high-level concepts).
    Include one or more code scenes only of asked or explanation calls for it to demonstrate practical usage. Ensure all code snippets adhere to the following formatting rules:use 4 spaces for indentation (no tabs),inline comments must have two spaces after the code before the comment starts,multi-line comments (if applicable) should be indented at the same level as the surrounding code,each line of code should not exceed 80 characters for readability.
    Include a sequence scene only if the topic involves system workflows, interactions, or processes. Otherwise, omit this scene type.
    Include an image+text scene only if the topic benefits from visual aids. Use Wikipedia topics to search for images.
    Include a multi-image+text scene only if the topic requires multiple images. Use Wikipedia topics to search for images.
    Include a triangle diagram scene only if the topic involves relationships between three elements. Use clear labels and voiceovers.
    Include a data processing flow scene only if the topic involves data processing. Use color-coded blocks and voiceovers.
    Include a timeline scene only if the topic has historical significance. Use years and events with voiceovers.
    Include a connection scene only if the topic involves connections between elements. Use clear labels and voiceovers.
    Replace placeholders with appropriate values for {topic}. Ensure the JSON is valid and responds only with the JSON, no additional text.
  """
    )

    try:
        print("Sending request to Azure OpenAI...")
        response = llm.complete(prompt_template.format(
            topic=topic,
            paper_context=paper_context,
            custom_instructions=custom_instructions
        ))
        print("Response received from Azure OpenAI")
        
        # Print the raw response for debugging
        print("\n--- RAW RESPONSE FROM AI ---")
        print(response.text[:500])  # Show first 500 chars
        print("..." if len(response.text) > 500 else "")
        print("---------------------------\n")
        
        result = clean_generated_text(response.text)
        
        # Print the cleaned JSON
        print("\n--- CLEANED JSON CONTENT ---")
        print(json.dumps(result, indent=2))
        print("---------------------------\n")
        
        return result
        
    except Exception as e:
        print(f"AI generation error: {str(e)}")
        raise ValueError(f"AI generation failed: {str(e)}")

def update_manim_config(output_name):
    """Update Manim configuration file with explicit settings"""
    config_parser = ConfigParser()
    config_path = 'manim.cfg'
    
    if os.path.exists(config_path):
        config_parser.read(config_path)
    else:
        config_parser.add_section('CLI')
    
    # Remove output_file setting
    if config_parser.has_option('CLI', 'output_file'):
        config_parser.remove_option('CLI', 'output_file')
    
    # Set other configurations
    config_parser.set('CLI', 'media_dir', MEDIA_ROOT)
    config_parser.set('CLI', 'quality', 'low_quality')
    config_parser.set('CLI', 'frame_rate', '30')
    config_parser.set('CLI', 'video_dir', VIDEO_DIR)
    config_parser.set('CLI', 'format', 'mp4')
    config_parser.set('CLI', 'disable_caching', 'True')
    config_parser.set('CLI', 'flush_cache', 'True')
    config_parser.set('CLI', 'write_to_movie', 'True')
    
    with open(config_path, 'w') as configfile:
        config_parser.write(configfile)
    
    print(f"Updated Manim config to disable caching and set video directory.")

def create_and_generate_video(topic, output_name, pdf_url=None, paper_title=None, user_description=None):
    """Main video creation workflow"""
    try:
        print("\n===== STARTING VIDEO CREATION WORKFLOW =====")

        # Clear cache FIRST
        clear_manim_cache(output_name)

        print(f"Topic: {topic}")
        print(f"Output name: {output_name}")
        
        # Ensure output directories exist
        os.makedirs(MEDIA_ROOT, exist_ok=True)
        os.makedirs(VIDEO_DIR, exist_ok=True)
        
        # Print environment info
        print("\nEnvironment:")
        print(f"Current directory: {os.getcwd()}")
        print(f"MEDIA_ROOT: {MEDIA_ROOT}")
        print(f"VIDEO_DIR: {VIDEO_DIR}")
        
        # Update manim config
        update_manim_config(output_name)
        
        # Generate video JSON
        print("\nGenerating video JSON...")
        video_json = generate_video_json_with_ai(topic, pdf_url=None, paper_title=None, user_description=None)

            # Force output name in JSON
        video_json['output_name'] = output_name
        print(f"Set output name in JSON to: {output_name}")
        
        # Add output_name to json if not present
        if 'output_name' not in video_json:
            video_json['output_name'] = output_name
            print(f"Added output_name '{output_name}' to JSON")
            
        # Generate video
        print("\nGenerating video from JSON...")
        generate_video_from_json(video_json)
        
        # Check if video was created
        output_path = os.path.join(VIDEO_DIR, f"{output_name}.mp4")
        max_wait = 20  # seconds
        wait_interval = 1  # second
        
        print(f"\nChecking for video at: {output_path}")
        for i in range(max_wait):
            if os.path.exists(output_path):
                print(f"✅ Video found after {i} seconds at: {output_path}")
                print(f"Video file size: {os.path.getsize(output_path)} bytes")
                return True
            print(f"Waiting for video... {i+1}/{max_wait} seconds")
            time.sleep(wait_interval)
            
        # Final check for video in any subdirectory
        print("\nPerforming final search for video file...")
        for root, dirs, files in os.walk(MEDIA_ROOT):
            for file in files:
                if file.endswith('.mp4') and output_name in file:
                    actual_path = os.path.join(root, file)
                    print(f"✅ Video found at: {actual_path}")
                    
                    # Copy to expected location if different
                    if actual_path != output_path:
                        import shutil
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        shutil.copy(actual_path, output_path)
                        print(f"Copied video to expected location: {output_path}")
                    
                    return True
        
        print("❌ Video file not found after extensive search")
        raise FileNotFoundError(f"Video file not created: {output_path}")
        
    except Exception as e:
        print(f"❌ Video creation failed: {str(e)}")
        import traceback
        print("--- TRACEBACK ---")
        print(traceback.format_exc())
        print("----------------")
        raise

@app.route('/generate_video', methods=['POST'])
def handle_generation():
    """Endpoint for video generation requests"""
    data = request.get_json()
    
    if not data or 'topic' not in data:
        return jsonify({"error": "Missing required parameter: topic"}), 400
        
    try:
        topic = data['topic']
        output_name = data.get('output_name', f"video_{int(time.time())}")
        pdf_url = data.get('pdf_url')
        paper_title = data.get('paper_title')
        user_description = data.get('user_description')
        
        print(f"\n----- RECEIVED REQUEST TO GENERATE VIDEO -----")
        print(f"Topic: {topic}")
        print(f"Output name: {output_name}")
        if pdf_url and paper_title:
            print(f"Paper source: {paper_title} ({pdf_url})")
        if user_description:
            print(f"User description: {user_description[:100]}...")

        # Create and generate video
        create_and_generate_video(
            topic=topic,
            output_name=output_name,
            pdf_url=pdf_url,
            paper_title=paper_title,
            user_description=user_description
        )
        
        # Define video URL after successful generation
        video_url = f"{request.host_url}media/videos/1080p60/{output_name}.mp4"
        
        print(f"\n✅ REQUEST SUCCESSFUL")
        print(f"Video URL: {video_url}")
        
        return jsonify({
            "status": "success",
            "video_url": video_url,
            "message": "Video generated successfully"
        }), 200
        
    except Exception as e:
        print(f"\n❌ REQUEST FAILED: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/media/videos/1080p60/<path:filename>')
def serve_video(filename):
    """Serve generated video files"""
    print(f"Serving video: {filename}")
    return send_from_directory(VIDEO_DIR, filename)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "video_generator"}), 200

if __name__ == '__main__':
    print("\n🚀 Starting Video Generator Service")
    print(f"Media directory: {MEDIA_ROOT}")
    print(f"Video directory: {VIDEO_DIR}")
    os.makedirs(VIDEO_DIR, exist_ok=True)
    print("Directories created")
    print("Server running at http://0.0.0.0:3000")
    app.run(host='0.0.0.0', port=3000, debug=True)