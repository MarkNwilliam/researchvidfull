import json
from manim import *
from manim import config
from manim_voiceover import VoiceoverScene
from code_video import CodeScene, AutoScaled, SequenceDiagram, TextBox, Connection
from manim_voiceover.services.azure import AzureService
from manim_voiceover.services.gtts import GTTSService
from code_video.widgets import DEFAULT_FONT
from manim.mobject.types.image_mobject import ImageMobject
import tempfile
import os
import shutil  # For directory removal
import requests
from PIL import Image
import io
from xml.etree import ElementTree
import cairosvg
import re
import json
import concurrent.futures

def remove_pango_markup(text):
    """Remove Pango Markup tags from a string."""
    if not isinstance(text, str):
        return text
    # Remove Pango Markup tags like <b>, <i>, etc.
    return re.sub(r'<[^>]+>', '', text)

def clean_json(json_data, scene_types_to_clean=None):
    """
    Recursively clean Pango Markup from specific fields in the JSON for specified scene types.
    
    Args:
        json_data (dict or list): The JSON data to clean.
        scene_types_to_clean (list): List of scene types to clean. If None, no filtering is applied.
    """
    if isinstance(json_data, dict):
        # Check if this is a scene and if its type matches the ones to clean
        if 'type' in json_data and (scene_types_to_clean is None or json_data['type'] in scene_types_to_clean):
            for key, value in json_data.items():
                # Clean specific fields for the matching scene types
                if key in ['main_text', 'subtitle', 'text', 'voiceover', 'event', 'narration']:
                    json_data[key] = remove_pango_markup(value)
        else:
            # Recursively clean nested dictionaries
            for key, value in json_data.items():
                clean_json(value, scene_types_to_clean)
    elif isinstance(json_data, list):
        # Recursively clean each item in the list
        for item in json_data:
            clean_json(item, scene_types_to_clean)
    return json_data

class DirectVideoGenerator(CodeScene, VoiceoverScene):
    def __init__(self, json_content):
        super().__init__()
        self.all_content = json_content if isinstance(json_content, dict) else json.loads(json_content)
        self.headers = {
            'User-Agent': 'DocVideoMaker/1.0 (https://example.com; contact@example.com)'
        }

        
    def create_title_scene(self, title_data):
        if 'background' in title_data:
            self.add_background(title_data['background'])
        else:
            self.add_background("./examples/resources/blackboard.jpg")
        
        with self.voiceover(title_data['voiceover']):
            # Automatically scale the main text to fit within the video width
            title = MarkupText(title_data['main_text'], font_size=48)
            title.width = min(title.width, config.frame_width * 0.8)  # Ensure it fits within 80% of the frame width
            title.move_to(ORIGIN)  # Center the title
            self.play(Create(title))
            
            if 'subtitle' in title_data:
                # Automatically scale the subtitle to fit within the video width
                subtitle = MarkupText(title_data['subtitle'], font_size=36)
                subtitle.width = min(subtitle.width, config.frame_width * 0.8)  # Ensure it fits within 80% of the frame width
                subtitle.next_to(title, direction=DOWN, buff=0.5)  # Add a margin below the title
                self.play(FadeIn(subtitle))
            
            self.wait(title_data.get('duration', 3))
        
        self.clear()

    def wrap_text(self, text, max_chars_per_line):
        """Return wrapped text as a string with newlines"""
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= max_chars_per_line:
                current_line += " " + word if current_line else word
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return "\n".join(lines)

    def create_overview_scene(self, overview_data):
        self.add_background("./examples/resources/blackboard.jpg")
      
        with self.voiceover(overview_data['voiceover']):
            if 'subtitle' in overview_data:
                subtitle = Title(overview_data['subtitle'])
                subtitle.scale(0.8)
                subtitle.to_edge(UP)
                self.play(FadeIn(subtitle, run_time=1.5))
                self.wait(overview_data.get('subtitle_duration', 0.5))
            
            text = AutoScaled(MarkupText(
                overview_data['text']
            ))
            self.play(FadeIn(text, run_time=2))
            self.wait(overview_data.get('duration', 0.5))
        
        self.clear()

    def create_code_scene(self, code_data):
        def format_code(code_text):
            """
            Format code by properly breaking it into lines and handling escape sequences
            """
            if isinstance(code_text, str):
                code_text = code_text.replace('\\n', '\n')
            
            lines = code_text.split('\n')
            formatted_lines = []
            
            for line in lines:
                line = line.rstrip()
                if not line:
                    formatted_lines.append('')
                    continue
                    
                if line.strip().startswith('#'):
                    formatted_lines.append(line)
                    continue
                
                if any(cmd in line.lower() for cmd in ['pip', 'wget', 'unzip', 'tar', 'selenium-driver']):
                    formatted_lines.append(line)
                    continue
                    
                formatted_lines.append(line)
                        
            final_lines = []
            for i, line in enumerate(formatted_lines):
                if line.strip().startswith('#') and i > 0 and not formatted_lines[i-1].strip().startswith('#') and formatted_lines[i-1].strip():
                    final_lines.append('')
                    
                final_lines.append(line)
                
                if any(cmd in line.lower() for cmd in ['pip install', 'wget', 'unzip', 'tar']):
                    final_lines.append('')
                        
            return '\n'.join(final_lines)

        try:
            formatted_code = format_code(code_data['code'])
            print("Formatted code:")
            print(formatted_code)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                temp_file.write(formatted_code)
                temp_path = temp_file.name

            try:
                tex = self.create_code(temp_path)
                
                with self.voiceover(code_data.get('intro_voiceover', f"Let's look at {code_data['title']}")):
                    self.play(Create(tex))
                self.wait(1)

                with self.voiceover(code_data['intro']['text']):
                    self.highlight_none(tex)
                    self.wait(1)

                total_lines = len(formatted_code.splitlines())
                print(f"Total lines after formatting: {total_lines}")

                for section in code_data['sections']:
                    print(f"Processing section: {section['title']}")
                    start_line = min(section['highlight_start'], total_lines)
                    end_line = min(section['highlight_end'], total_lines)
                    
                    with self.voiceover(section['voiceover']):
                        self.highlight_lines(
                            tex, 
                            start_line,
                            end_line,
                            section['title']
                        )
                        self.wait(section.get('duration', 2))

                with self.voiceover(code_data['conclusion']['text']):
                    self.highlight_none(tex)
                    self.wait(2)

            finally:
                os.unlink(temp_path)
            
            self.clear()
            
        except Exception as e:
            print(f"Error in create_code_scene: {type(e).__name__}: {e}")
            print(f"Current code structure:")
            print(formatted_code)
            raise

    def create_sequence_diagram(self, sequence_data):
        print("here is the sequence data", sequence_data)   
        background_path = sequence_data.get('background')
        if background_path:
            self.add_background(background_path)
        else:
            self.add_background("./examples/resources/blackboard.jpg")
        
        if 'title' in sequence_data:
            title = Text(sequence_data['title'], font=DEFAULT_FONT)
            title.scale(0.8)
            title.to_edge(UP)
            self.add(title)

        diagram = AutoScaled(SequenceDiagram())
        actors = {}
        actor_names = sequence_data["actors"]
        actor_objects = diagram.add_objects(*actor_names)
        
        for name, obj in zip(actor_names, actor_objects):
            actors[name] = obj

        for interaction in sequence_data["interactions"]:
            source = actors[interaction["from"]]
            
            if interaction["type"] == "note":
                source.note(
                    message=interaction["message"],
                    voiceover=interaction["voiceover"]
                )
            else:
                target = actors[interaction["to"]]
                source.to(
                    target,
                    message=interaction["message"],
                    voiceover=interaction["voiceover"]
                )

        title = Text(sequence_data["title"], font=DEFAULT_FONT)
        title.scale(0.8)
        title.to_edge(UP)

        self.add(title)
        diagram.next_to(title, DOWN)
        self.play(Create(diagram))

        self.create_diagram_with_voiceover(diagram)
        self.wait(0.4)
        self.clear()

    def add_background(self, path):
        try:
            background = ImageMobject(path)
            self.add(background)
        except OSError as e:
            print(f"Error loading background image: {e}")
    

    def get_wikipedia_images(self, article_title, num_images=2, save_dir="./downloaded_images"):
            """Fetch images from Wikipedia article, including SVGs converted to PNG."""
            import concurrent.futures
            import os
            import requests
            from PIL import Image
            import cairosvg

            os.makedirs(save_dir, exist_ok=True)

            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "titles": article_title,
                "prop": "images",
                "imlimit": 50  # Increased limit
            }

            response = requests.get(url, params=params, headers=self.headers)
            data = response.json()
            print("Image data:", data)

            pages = data.get("query", {}).get("pages", {})
            page_id = list(pages.keys())[0] if pages else None

            if not page_id or "missing" in pages[page_id]:
                print(f"No article found for topic: {article_title}. Searching for related articles...")
                search_url = "https://en.wikipedia.org/w/api.php"
                search_params = {
                    "action": "query",
                    "format": "json",
                    "list": "search",
                    "srsearch": article_title,
                    "srlimit": 1
                }
                search_response = requests.get(search_url, params=search_params, headers=self.headers)
                search_data = search_response.json()
                print("Search response:", search_data)

                if "query" in search_data and "search" in search_data["query"]:
                    article_title = search_data["query"]["search"][0]["title"]
                    print(f"Using related article: {article_title}")
                else:
                    print(f"No related articles found for topic: {article_title}")
                    return []

            params["titles"] = article_title
            response = requests.get(url, params=params, headers=self.headers)
            data = response.json()
            print("Updated image data:", data)

            pages = data.get("query", {}).get("pages", {})
            page_id = list(pages.keys())[0] if pages else None
            if not page_id or "images" not in pages[page_id]:
                print(f"No images found for the article: {article_title}")
                return []

            # Include SVGs in the filtered image titles
            image_titles = [
                img["title"] for img in pages[page_id]["images"]
                if "logo" not in img["title"].lower() and "icon" not in img["title"].lower()
            ]
            print("Filtered image titles:", image_titles)

            image_titles = image_titles[:num_images]
            image_paths = []

            def download_single_image(title):
                img_params = {
                    "action": "query",
                    "format": "json",
                    "titles": title,
                    "prop": "imageinfo",
                    "iiprop": "url"
                }

                img_response = requests.get(url, params=img_params, headers=self.headers)
                img_data = img_response.json()
                print("Image URL data:", img_data)

                img_pages = img_data.get("query", {}).get("pages", {})
                img_id = list(img_pages.keys())[0] if img_pages else None
                if img_id and "imageinfo" in img_pages[img_id]:
                    img_url = img_pages[img_id]["imageinfo"][0]["url"]
                    print("Downloading image from:", img_url)

                    try:
                        img_response = requests.get(img_url, headers=self.headers)
                        img_response.raise_for_status()

                        file_name = os.path.basename(img_url)
                        save_path = os.path.join(save_dir, file_name)
                        with open(save_path, "wb") as img_file:
                            img_file.write(img_response.content)

                        # Convert SVG to PNG if needed
                        if file_name.lower().endswith(".svg"):
                            try:
                                png_path = save_path.rsplit('.', 1)[0] + '.png'
                                cairosvg.svg2png(url=save_path, write_to=png_path)
                                print(f"Converted SVG to PNG: {png_path}")
                                
                                # Remove the original SVG file
                                os.unlink(save_path)
                                
                                # Verify the PNG
                                with Image.open(png_path) as img:
                                    img.verify()
                                
                                return png_path
                            except Exception as e:
                                print(f"Error converting SVG to PNG: {e}")
                                return None

                        # For non-SVG images, use existing verification
                        else:
                            try:
                                with Image.open(save_path) as img:
                                    img.verify()
                                return save_path
                            except Exception as e:
                                print(f"Invalid image file: {save_path}, error: {e}")
                                os.unlink(save_path)
                                return None

                    except Exception as e:
                        print(f"Error downloading image: {e}")
                        return None

            # Use ThreadPoolExecutor for parallel downloads
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(image_titles))) as executor:
                # Map the download function to image titles
                future_to_title = {executor.submit(download_single_image, title): title for title in image_titles}
                
                for future in concurrent.futures.as_completed(future_to_title):
                    result = future.result()
                    if result:
                        image_paths.append(result)

            print("Downloaded image paths:", image_paths)
            return image_paths

    def create_image_text_scene(self, scene_data):
        """Scene with title, text, and Wikipedia images"""
        self.add_background("./examples/resources/blackboard.jpg")
        
        with self.voiceover(scene_data['voiceover']):
            title = Title(scene_data['title'])
            title.to_edge(UP)
            self.play(FadeIn(title, run_time=1))
            
            text = AutoScaled(MarkupText(scene_data['text']))
            text.next_to(title, DOWN, buff=0.5)
            self.play(FadeIn(text, run_time=1))
            
            num_images = scene_data.get('num_images', 2)
            image_paths = self.get_wikipedia_images(scene_data['wikipedia_topic'], num_images)
            
            images = []
            if not image_paths:
                for i in range(num_images):
                    placeholder = Rectangle(width=4, height=3, color=RED)
                    placeholder_text = Text(f"No image {i+1} found", font_size=20).move_to(placeholder.get_center())
                    images.append(Group(placeholder, placeholder_text))
            else:
                for path in image_paths:
                    try:
                        img = ImageMobject(path)
                        img.width = 3
                        images.append(img)
                    except Exception as e:
                        print(f"Error loading image: {e}")
                        placeholder = Rectangle(width=3, height=2.25, color=RED)
                        placeholder_text = Text("Image load failed", font_size=18).move_to(placeholder.get_center())
                        images.append(Group(placeholder, placeholder_text))
            
            image_group = Group(*images).arrange(RIGHT, buff=0.5)
            image_group.next_to(text, DOWN, buff=0.5)
            
            for img in images:
                self.play(FadeIn(img, run_time=0.5))
            
            self.wait(scene_data.get('duration', 5))
        
        self.clear()

    def create_multi_image_text_scene(self, image_text_data):
        """Scene with multiple images and text"""
        print(f"Creating scene: {image_text_data.get('title', 'Untitled')}")
        print(f"Image paths: {image_text_data.get('image_paths', [])}")
        self.add_background("./examples/resources/blackboard.jpg")
        
        with self.voiceover(image_text_data['voiceover']):
            if 'title' in image_text_data:
                title = Title(image_text_data['title'])
                title.to_edge(UP)
                self.play(FadeIn(title, run_time=1))
            
            images = []
            if 'wikipedia_topics' in image_text_data:
                num_images = image_text_data.get('num_images', 2)
                keywords = image_text_data['wikipedia_topics']
                print(f"Searching for images using keywords: {keywords}")
                
                image_paths = []
                for keyword in keywords:
                    print(f"Trying keyword: {keyword}")
                    image_paths = self.get_wikipedia_images(keyword, num_images)
                    if image_paths:
                        print(f"Images found for keyword: {keyword}")
                        break
                    else:
                        print(f"No images found for keyword: {keyword}")
                
                if not image_paths:
                    print(f"No images found for any of the keywords: {keywords}")
                    for i in range(num_images):
                        print(f"Creating placeholder for image {i+1}")
                        placeholder = Rectangle(width=4, height=3, color=RED)
                        placeholder_text = Text(f"No image {i+1} found", font_size=20).move_to(placeholder.get_center())
                        images.append(Group(placeholder, placeholder_text))
                else:
                    for path in image_paths:
                        print(f"\n--- Attempting to load image: {path} ---")
                        print(f"Image path exists: {os.path.exists(path)}")
                        if os.path.exists(path):
                            print(f"Image path permissions: {oct(os.stat(path).st_mode)[-3:]}")
                            print(f"Image file size: {os.path.getsize(path)} bytes")
                        
                        try:
                            print("Loading image with ImageMobject...")
                            img = ImageMobject(path)
                            print(f"Image loaded successfully - dimensions: {img.width} x {img.height}")
                            
                            if 'image_width' in image_text_data:
                                print(f"Setting custom width: {image_text_data['image_width']}")
                                img.width = image_text_data['image_width']
                            else:
                                print("Setting default width: 3")
                                img.width = 3
                            
                            print("Adding image to collection")
                            images.append(img)
                            
                        except Exception as e:
                            print(f"Error loading image: {str(e)}")
                            print(f"Error type: {type(e).__name__}")
                            print("Creating placeholder for failed image")
                            placeholder = Rectangle(width=3, height=2.25, color=RED)
                            placeholder_text = Text("Image load failed", font_size=18)
                            placeholder_text.move_to(placeholder.get_center())
                            images.append(Group(placeholder, placeholder_text))
            
            elif 'image_paths' in image_text_data:
                for path in image_text_data['image_paths']:
                    try:
                        img = ImageMobject(path)
                        if 'image_width' in image_text_data:
                            img.width = image_text_data['image_width']
                        else:
                            img.width = 3
                        images.append(img)
                    except Exception as e:
                        print(f"Error loading image: {e}")
                        placeholder = Rectangle(width=3, height=2.25, color=RED)
                        placeholder_text = Text("Image load failed", font_size=18).move_to(placeholder.get_center())
                        images.append(Group(placeholder, placeholder_text))
            
            text = AutoScaled(MarkupText(image_text_data['text']))
            
            layout = image_text_data.get('layout', 'horizontal')
            image_group = None
            
            if layout == 'horizontal':
                image_group = Group(*images).arrange(RIGHT, buff=0.5)
            else:
                image_group = Group(*images).arrange(DOWN, buff=0.5)
            
            if 'title' in image_text_data:
                text.next_to(title, DOWN, buff=0.5)
                image_group.next_to(text, DOWN, buff=0.5)
            else:
                text.to_edge(UP, buff=1)
                image_group.next_to(text, DOWN, buff=0.5)
            
            full_group = Group(text, image_group)
            full_group.move_to(ORIGIN)
            
            self.play(FadeIn(text), run_time=1)
            for img in images:
                self.play(FadeIn(img), run_time=0.5)
            
            self.wait(image_text_data.get('duration', 5))

    def create_triangle_scene(self, triangle_data):
        """Scene with three connected components in a triangle layout"""
        self.add_background("./examples/resources/blackboard.jpg")
        
        with self.voiceover(triangle_data['voiceover']):
            if 'title' in triangle_data:
                title = Title(triangle_data['title'])
                title.to_edge(UP)
                self.play(FadeIn(title, run_time=1))
                
            top = TextBox(triangle_data['top_text'], shadow=False)
            left = TextBox(triangle_data['left_text'], shadow=False)
            right = TextBox(triangle_data['right_text'], shadow=False)
            
            if 'title' in triangle_data:
                top.next_to(title, DOWN, buff=1)
            else:
                top.move_to(UP)
                
            left.next_to(top, DOWN + LEFT, buff=2)
            right.next_to(top, DOWN + RIGHT, buff=2)
            
            connections = []
            
            if 'top_to_left' in triangle_data:
                conn1 = Connection(top, left, triangle_data['top_to_left'])
                connections.append(conn1)
                
            if 'top_to_right' in triangle_data:
                conn2 = Connection(top, right, triangle_data['top_to_right'], padding=-0.7)
                connections.append(conn2)
                
            if 'left_to_right' in triangle_data:
                conn3 = Connection(left, right, triangle_data['left_to_right'])
                connections.append(conn3)
                
            if 'right_to_left' in triangle_data:
                conn4 = Connection(right, left, triangle_data['right_to_left'])
                connections.append(conn4)
                
            if 'left_to_top' in triangle_data:
                conn5 = Connection(left, top, triangle_data['left_to_top'])
                connections.append(conn5)
                
            if 'right_to_top' in triangle_data:
                conn6 = Connection(right, top, triangle_data['right_to_top'], padding=-0.6)
                connections.append(conn6)
            
            elements = VGroup(top, left, right, *connections)
            auto_scaled_elements = AutoScaled(elements)
            
            self.play(FadeIn(top))
            
            if connections:
                for i, conn in enumerate(connections):
                    self.play(Create(conn))
                    if i == 0 and 'top_to_left' in triangle_data:
                        self.play(FadeIn(left))
                    elif i == 1 and 'top_to_right' in triangle_data:
                        self.play(FadeIn(right))
                    if i == len(connections) - 1:
                        remaining = []
                        if 'top_to_left' not in triangle_data and left not in self.mobjects:
                            remaining.append(left)
                        if 'top_to_right' not in triangle_data and right not in self.mobjects:
                            remaining.append(right)
                        if remaining:
                            self.play(*[FadeIn(mob) for mob in remaining])
            else:
                self.play(FadeIn(left), FadeIn(right))
            
            self.wait(triangle_data.get('duration', 5))
        
        self.clear()

    def create_data_processing_flow(self, flow_data):
        """Data processing flow animation"""
        color_map = {
            "green": GREEN,
            "red": RED,
            "blue": BLUE,
            "purple": PURPLE
        }

        self.add_background("./examples/resources/blackboard.jpg")

        blocks = []
        for block_config in flow_data['blocks']:
            block = Rectangle(width=2, height=1, color=color_map[block_config['color']], fill_opacity=0.3)
            
            block_text = Text(block_config['text'], font_size=20, color=WHITE)
            margin = 0.2
            while block_text.width > block.width - margin or block_text.height > block.height - margin:
                block_text.scale(0.9)
            
            text_background = Rectangle(
                width=block_text.width + 0.2,
                height=block_text.height + 0.2,
                color=BLACK,
                fill_opacity=0.5,
                stroke_opacity=0
            )
            text_background.move_to(block_text.get_center())
            
            text_group = VGroup(text_background, block_text)
            text_group.move_to(block.get_center())
            
            block_group = VGroup(block, text_group)
            blocks.append((block_group, block_config))

        blocks[0][0].shift(LEFT*3 + UP*1.5)
        blocks[1][0].shift(LEFT*3 + DOWN*1.5)
        blocks[2][0].shift(ORIGIN)
        blocks[3][0].shift(RIGHT*3)

        arrows = [
            Line(blocks[0][0].get_right(), blocks[2][0].get_left(), color=GREEN, tip_length=0.1).add_tip(),
            Line(blocks[1][0].get_right(), blocks[2][0].get_left(), color=RED, tip_length=0.1).add_tip(),
            Line(blocks[2][0].get_right(), blocks[3][0].get_left(), color=PURPLE, tip_length=0.1).add_tip()
        ]

        for block, block_config in blocks:
            with self.voiceover(text=block_config['voiceover']):
                if block_config['type'] in ['input1', 'input2']:
                    self.play(FadeIn(block))
                elif block_config['type'] == 'processor':
                    self.play(
                        Create(arrows[0]),
                        Create(arrows[1]),
                        FadeIn(block)
                    )
                elif block_config['type'] == 'output':
                    self.play(
                        Create(arrows[2]),
                        FadeIn(block)
                    )

        with self.voiceover(text=flow_data['narration']['conclusion']):
            self.wait(1)

        self.play(
            *[FadeOut(block) for block, _ in blocks],
            *[FadeOut(arrow) for arrow in arrows]
        )

    def create_timeline_scene(self, timeline_data):
        """
        Creates a timeline animation scene with events, images, and narration.

        Parameters:
        timeline_data (dict): A dictionary containing the timeline scene data.
            - 'title' (str): Title for the timeline (optional).
            - 'events' (list): List of events, each with:
                - 'year' (str/int): Year or time marker for the event.
                - 'text' (str): Short description of the event.
                - 'narration' (str): Voiceover text for the event.
                - 'image_description' (str): Search term for wikimedia image (optional).
            - 'background_image' (str): Path to background image (optional).
        """
        # Use specified background or default
        background_image_path = timeline_data.get('background_image', 
                                                "./examples/resources/blackboard.jpg")
        background = ImageMobject(background_image_path)
        background.scale_to_fit_width(config.frame_width * 3)
        background.scale_to_fit_height(config.frame_height * 3)
        background.move_to(ORIGIN)
        self.add(background)

        # Reuse headers from TimelineAnimation for API requests
        self.headers = {
            'User-Agent': 'TimelineAnimation/1.0 (https://example.com; contact@example.com)'
        }

        # Set up timeline
        events = [(event['year'], event['text'], event['narration'], event.get('image_description', '')) 
                for event in timeline_data['events']]

        num_events = len(events)
        timeline = Line(LEFT * 7, RIGHT * 7, color=WHITE)
        timeline_group = Group(timeline)

        # Create elements containers
        dots = Group()
        year_labels = Group()
        event_texts = Group()
        images = Group()

        # Pre-calculate positions
        positions = [timeline.point_from_proportion(i / (num_events - 1)) for i in range(num_events)]

        # Add title if specified
        if 'title' in timeline_data:
            title = Title(timeline_data['title'])
            title.to_edge(UP, buff=0.5)
            self.play(FadeIn(title))

        for i, (year, text, _, image_desc) in enumerate(events):
            # Create timeline elements
            dot = Dot(color=BLUE).move_to(positions[i])
            year_label = Text(str(year), font_size=20).next_to(dot, UP, buff=0.15)

            # Format text with line breaks
            words = text.split()
            lines = [" ".join(words[i:i + 3]) for i in range(0, len(words), 3)]
            event_text = Text("\n".join(lines), font_size=16, line_spacing=0.8)
            event_text.next_to(dot, DOWN, buff=0.25 + (0.1 * len(lines)))

            # Image handling
            if image_desc:
                image_path = self.get_wikimedia_image(image_desc)
                if image_path and os.path.exists(image_path):
                    try:
                        img = ImageMobject(image_path)
                        img = self.scale_image(img)
                        img.next_to(year_label, UP, buff=0.25)
                        # Add background rectangle
                        bg = BackgroundRectangle(img, fill_opacity=0.6, buff=0.1)
                        image_mob = Group(bg, img)
                        images.add(image_mob)  # Add only if the image exists
                    except Exception as e:
                        print(f"Error loading image: {e}")
            # Add other elements to their respective groups
            dots.add(dot)
            year_labels.add(year_label)
            event_texts.add(event_text)

        # Add all elements to timeline group
        timeline_group.add(dots, year_labels, event_texts, images)
        timeline_group.center()

        # Animation sequence
        self.play(Create(timeline))
        self.wait(0.5)

        # Set up camera for MovingCameraScene functionality
        self.camera.frame.scale(1.2)

        for i in range(num_events):
            with self.voiceover(text=events[i][2]) as tracker:
                # Animate elements with adjusted timing
                self.play(
                    FadeIn(dots[i]),
                    FadeIn(year_labels[i]),
                    FadeIn(event_texts[i]),
                    FadeIn(images[i]),
                    self.camera.frame.animate.move_to(dots[i]).scale(0.5),
                    run_time=tracker.duration * 0.4
                )
                # Hold position for clearer view
                self.wait(tracker.duration * 0.2)
                # Smooth return to timeline view
                self.play(
                    self.camera.frame.animate.move_to(ORIGIN).scale(1 / 0.5),
                    run_time=tracker.duration * 0.4
                )

        # Clear the scene
        self.clear()

    def create_error_placeholder(self):
        error_mob = Rectangle(width=1.5, height=1, color=RED)
        error_text = Text("Image Error", font_size=14).move_to(error_mob.get_center())
        return Group(error_mob, error_text)

    def create_missing_placeholder(self):
        missing_mob = Rectangle(width=1.5, height=1, color=BLUE_E)
        missing_text = Text("No Image", font_size=14).move_to(missing_mob.get_center())
        return Group(missing_mob, missing_text)

    def scale_image(self, img_mob, max_width=2.5, max_height=1.8):
        width = img_mob.width
        height = img_mob.height
        
        width_scale = max_width / width
        height_scale = max_height / height
        
        scale_factor = min(width_scale, height_scale)
        return img_mob.scale(scale_factor * 0.9)
    

    def get_wikimedia_image(self, search_term, save_dir="./downloaded_images"):
        """Fetch image from Wikimedia"""
        print(f"Searching Wikimedia for: {search_term}")
        
        os.makedirs(save_dir, exist_ok=True)

        try:
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": search_term,
                "srlimit": 3
            }
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params=search_params,
                headers=self.headers
            )
            data = response.json()
            print(f"Search response: {data}")

            if "query" in data and data["query"]["search"]:
                article_title = data["query"]["search"][0]["title"]
                print(f"Found article: {article_title}")
                
                # First attempt: Try to find non-SVG images
                img_params = {
                    "action": "query",
                    "format": "json",
                    "titles": article_title,
                    "prop": "images",
                    "imlimit": 10
                }
                img_response = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params=img_params,
                    headers=self.headers
                )
                img_data = img_response.json()
                print(f"Image data: {img_data}")
                
                pages = img_data["query"]["pages"]
                page_id = list(pages.keys())[0]
                
                # First try: Non-SVG images
                if "images" in pages[page_id]:
                    image_titles = [
                        img["title"] for img in pages[page_id]["images"]
                        if not img["title"].lower().endswith(".svg") 
                        and "logo" not in img["title"].lower()
                        and "icon" not in img["title"].lower()
                    ]
                    print(f"Filtered non-SVG image titles: {image_titles}")
                    
                    # If no non-SVG images found, try SVG images
                    if not image_titles:
                        image_titles = [
                            img["title"] for img in pages[page_id]["images"]
                            if img["title"].lower().endswith(".svg") 
                            and "logo" not in img["title"].lower()
                            and "icon" not in img["title"].lower()
                        ]
                        print(f"Filtered SVG image titles: {image_titles}")
                    
                    if image_titles:
                        img_info_params = {
                            "action": "query",
                            "format": "json",
                            "titles": image_titles[0],
                            "prop": "imageinfo",
                            "iiprop": "url"
                        }
                        img_info_response = requests.get(
                            "https://en.wikipedia.org/w/api.php",
                            params=img_info_params,
                            headers=self.headers
                        )
                        img_info_data = img_info_response.json()
                        print(f"Image info data: {img_info_data}")
                        
                        img_info_pages = img_info_data["query"]["pages"]
                        img_info_id = list(img_info_pages.keys())[0]
                        
                        if "imageinfo" in img_info_pages[img_info_id]:
                            img_url = img_info_pages[img_info_id]["imageinfo"][0]["url"]
                            print(f"Found image URL: {img_url}")
                            
                            try:
                                img_response = requests.get(img_url, headers=self.headers)
                                img_response.raise_for_status()
                                
                                if "image" not in img_response.headers.get("Content-Type", ""):
                                    print(f"Invalid content type for URL: {img_url}")
                                    return None
                                
                                file_name = os.path.basename(img_url)
                                save_path = os.path.join(save_dir, file_name)
                                with open(save_path, "wb") as img_file:
                                    img_file.write(img_response.content)
                                
                                # Special handling for SVG files
                                if file_name.lower().endswith(".svg"):
                                    try:
                                        import cairosvg
                                        png_path = save_path.rsplit('.', 1)[0] + '.png'
                                        cairosvg.svg2png(url=save_path, write_to=png_path)
                                        print(f"Converted SVG to PNG: {png_path}")
                                        
                                        # Remove the original SVG file
                                        os.unlink(save_path)
                                        save_path = png_path
                                    except Exception as svg_err:
                                        print(f"Error converting SVG: {svg_err}")
                                        return None
                                
                                try:
                                    with Image.open(save_path) as img:
                                        img.verify()
                                    print(f"Image saved and validated: {save_path}")
                                    return save_path
                                except Exception as e:
                                    print(f"Invalid image file: {save_path}, error: {e}")
                                    os.unlink(save_path)
                                    return None
                            
                            except Exception as img_err:
                                print(f"Error downloading or processing image: {img_err}")
                                return None
            
            print(f"No image found for: {search_term}")
            return None
        
        except Exception as e:
            print(f"Error in get_wikimedia_image: {str(e)}")
            return None

    def goodbye(self):
        text = Text(
            "Thank you for watching! You can generate other tutorial videos with our platform.",
            font_size=40
        )
        text.width = min(text.width, config.frame_width * 0.8)  # Ensure it fits within 80% of the frame width
        text.move_to(ORIGIN)

        with self.voiceover(text="Thank you for watching! You can generate other tutorial videos with our platform.") as tracker:
            self.play(FadeIn(text), run_time=tracker.duration)
        
        self.wait(0.5)
        self.play(*[FadeOut(mob) for mob in self.mobjects])

    def construct(self):
        # Commented out GTTS service
        # try:
        #     self.set_speech_service(GTTSService())
        #     print("Using Google Text-to-Speech service")
        # except Exception as e:
        #     print(f"Error setting up GTTS: {e}")
        
        try:
            self.set_speech_service(AzureService(voice="en-US-SteffanNeural", style="newscast"))
            print("Using Azure Text-to-Speech service")
        except Exception as e2:
            print(f"Error setting up Azure TTS: {e2}")
            print("WARNING: No speech service available!")
        
        if self.all_content.get('background_music'):
            try:
                self.add_background_music(self.all_content['background_music'])
                print(f"Added background music: {self.all_content['background_music']}")
            except Exception as e:
                print(f"Error adding background music: {e}")
        
        for scene in self.all_content['scenes']:
            scene_type = scene['type']
            print(f"Processing scene of type: {scene_type}")
            
            try:
                if scene_type == 'title':
                    self.create_title_scene(scene)
                elif scene_type == 'overview':
                    self.create_overview_scene(scene)
                elif scene_type == 'code':
                    self.create_code_scene(scene)
                elif scene_type == 'sequence':
                    self.create_sequence_diagram(scene)
                elif scene_type == 'image_text':
                    self.create_image_text_scene(scene)
                elif scene_type == 'multi_image_text':
                    self.create_multi_image_text_scene(scene)
                elif scene_type == 'triangle':
                    self.create_triangle_scene(scene)
                elif scene_type == 'timeline':
                    self.create_timeline_scene(scene)
                elif scene_type == 'data_processing_flow':
                    self.create_data_processing_flow(scene)
                else:
                    print(f"Warning: Unknown scene type: {scene_type}")
            except Exception as e:
                print(f"Error processing {scene_type} scene: {e}")
            
            if scene != self.all_content['scenes'][-1]:
                try:
                    with self.voiceover(scene.get('transition_text', 'Moving on.')):
                        self.clear()
                        self.wait(0.5)
                except Exception as e:
                    print(f"Error with transition: {e}")
                
                self.clear()
                self.wait(0.5)
        
        try:
            self.goodbye()
        except Exception as e:
            print(f"Error with goodbye scene: {e}")

def generate_video_from_json(json_content):
    """Generate video from JSON with dynamic scene naming"""
    output_name = json_content.get('output_name', 'GeneratedVideo')
    print(f"Generating video with output_name: {output_name}")

    config.output_file = ""
    config.disable_caching = True
    config.flush_cache = True
    config.write_to_movie = True
    config.format = 'mp4'
    config.frame_rate = 30
    config.quality = "low_quality"
    config.tex_template = "custom_template.tex"
    
    config.partial_movie_dir = os.path.join(config.video_dir, "partial_movie_files", output_name)
    
    print(f"Current config output_file: {config.output_file}")
    print(f"Using scene name: {output_name}")
    
    DynamicScene = type(
        output_name, 
        (DirectVideoGenerator,),
        {'__module__': __name__}
    )
    
    print(f"DynamicScene class name: {DynamicScene.__name__}")
    
    scene = DynamicScene(json_content)
    scene.add_background("./examples/resources/blackboard.jpg") 
    scene.render()

    temp_files = [
        f"{output_name}.log",
        f"media/tex_files/{output_name}",
        f"media/texts/{output_name}"
    ]
    for f in temp_files:
        if os.path.exists(f):
            try:
                if os.path.isdir(f):
                    shutil.rmtree(f)
                else:
                    os.remove(f)
            except Exception as e:
                print(f"Warning: Failed to clean up {f}: {str(e)}")

# Example JSON content
example_json = {
  "output_name": "LatticeQCDandEpsilonK",
  "scenes": [
    {
      "type": "title",
      "main_text": "<b>Understanding $\\epsilon K$ in Lattice QCD</b>",
      "subtitle": "A deep dive into the role of $\\epsilon K$ in Quantum Chromodynamics",
      "voiceover": "Welcome to our exploration of $\\epsilon K$ in Lattice Quantum Chromodynamics. We'll delve into the intricacies of this fascinating topic.",
      "duration": 5
    },
    {
      "type": "overview",
      "text": "Lattice Quantum Chromodynamics (QCD) is a non-perturbative approach to solving the quantum chromodynamics theory of quarks and gluons. $\\epsilon K$ is a parameter that measures indirect CP violation in the neutral kaon system.",
      "voiceover": "In this video, we'll be focusing on $\\epsilon K$, a parameter that plays a crucial role in Lattice QCD. $\\epsilon K$ measures indirect CP violation in the neutral kaon system, a key aspect of quantum chromodynamics.",
      "creation_time": 10,
      "duration": 4,
      "subtitle": "Exploring $\\epsilon K$ in the realm of Quantum Chromodynamics"
    },
    {
      "type": "code",
      "title": "Calculating $\\epsilon K$",
      "code": "import numpy as np\n\n# Define the CP violation parameter\nepsilon_K = 0.228\n\n# Calculate the indirect CP violation\nindirect_CP_violation = np.abs(epsilon_K)\nprint(indirect_CP_violation)",
      "intro": {
        "text": "Here's a simple Python code snippet to calculate the absolute value of $\\epsilon K$, representing the indirect CP violation.",
        "voiceover": "Let's look at a simple Python code snippet. Here, we're calculating the absolute value of $\\epsilon K$, which gives us the indirect CP violation."
      },
      "sections": [
        {
          "title": "Code Explanation",
          "highlight_start": 1,
          "highlight_end": 5,
          "voiceover": "We start by importing numpy. Then we define $\\epsilon K$, the CP violation parameter. Finally, we calculate the indirect CP violation by finding the absolute value of $\\epsilon K$.",
          "duration": 3
        }
      ],
      "conclusion": {
        "text": "This code provides a simple way to calculate the indirect CP violation using $\\epsilon K$.",
        "voiceover": "So, this code snippet provides a straightforward way to calculate the indirect CP violation using the $\\epsilon K$ parameter."
      }
    },
    {
      "type": "image_text",
      "title": "Visualizing $\\epsilon K$",
      "text": "The $\\epsilon K$ parameter is a key factor in understanding the complex world of quantum chromodynamics. It helps us understand the indirect CP violation in the neutral kaon system.",
      "voiceover": "The $\\epsilon K$ parameter is crucial in the realm of quantum chromodynamics. It provides insights into the indirect CP violation in the neutral kaon system.",
      "wikipedia_topic": "CP_violation",
      "num_images": 2,
      "duration": 6
    },
    {
      "type": "timeline",
      "title": "Historical Significance of $\\epsilon K$",
      "events": [
        {
          "year": 1964,
          "text": "Discovery of CP violation",
          "narration": "In 1964, the concept of CP violation, which $\\epsilon K$ measures, was discovered.",
          "image_description": "CP_violation"
        },
        {
          "year": 1973,
          "text": "Introduction of Quantum Chromodynamics",
          "narration": "Quantum Chromodynamics, the theory in which $\\epsilon K$ plays a crucial role, was introduced in 1973.",
          "image_description": "Quantum_Chromodynamics"
        }
      ]
    },
    {
      "type": "data_processing_flow",
      "blocks": [
        {
          "type": "input",
          "text": "$\\epsilon K$ value",
          "voiceover": "We start with the $\\epsilon K$ value, which is the input for our calculation.",
          "color": "blue"
        },
        {
          "type": "processor",
          "text": "Calculate indirect CP violation",
          "voiceover": "We then calculate the indirect CP violation using the $\\epsilon K$ value.",
          "color": "green"
        },
        {
          "type": "output",
          "text": "Indirect CP violation",
          "voiceover": "The output is the indirect CP violation in the neutral kaon system.",
          "color": "red"
        }
      ],
      "narration": {
        "conclusion": "This flow shows how the $\\epsilon K$ value is used to calculate the indirect CP violation."
      }
    }
  ]
}
# Clean only the "overview" and "timeline" scene types
cleaned_json = clean_json(example_json, scene_types_to_clean=['timeline', 'sequence'])
print(json.dumps(cleaned_json, indent=2))

if __name__ == "__main__":
    # Use directly with JSON
    generate_video_from_json(example_json)