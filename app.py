from flask import Flask, render_template, request, send_file, jsonify
from PyPDF2 import PdfReader
from gtts import gTTS
from pydub import AudioSegment
import os
from googletrans import Translator
import threading
import uuid
import time
from pathlib import Path
import logging
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
from textwrap import wrap

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_directories():
    directories = ['uploads', 'output', 'temp']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

# Call ensure_directories after defining it
ensure_directories()

# Global dictionary to store progress information
progress_dict = {}

# Mapping language codes and TLDs for accents
language_map = {
    "en": {"lang": "en", "tld": "com"},
    "en-uk": {"lang": "en", "tld": "co.uk"},
    "pt": {"lang": "pt", "tld": "com.br"},
    "es": {"lang": "es", "tld": "com"},
    "fr": {"lang": "fr", "tld": "fr"},
    "de": {"lang": "de", "tld": "de"},
    "it": {"lang": "it", "tld": "it"},
    "zh-CN": {"lang": "zh-CN", "tld": "com"},
    "ja": {"lang": "ja", "tld": "co.jp"}
}

def extract_text_chunks_from_pdf(pdf_path, max_chunk_length=500):
    try:
        reader = PdfReader(pdf_path)
        chunks = []
        current_chunk = ''
        
        # Add progress tracking for PDF reading
        total_pages = len(reader.pages)
        for page_num, page in enumerate(reader.pages):
            # Free up memory after every few pages
            if page_num % 10 == 0:
                import gc
                gc.collect()
            
            page_text = page.extract_text()
            if not page_text:
                continue
                
            # Split by sentences instead of words for more natural breaks
            sentences = page_text.replace('\n', ' ').split('. ')
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > max_chunk_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + '. '
                else:
                    current_chunk += sentence + '. '
                    
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks
    except Exception as e:
        raise Exception(f"Error extracting text from PDF: {e}")

def convert_text_to_audio(text, output_filename, voice, speed, tld='com'):
    try:
        temp_output = os.path.join('temp', output_filename.replace(".mp3", "_temp.mp3"))
        output_path = os.path.join('temp', output_filename)
        tts = gTTS(text, lang=voice, tld=tld)
        tts.save(temp_output)

        # Adjust the speed if necessary
        if speed != 1.0:
            sound = AudioSegment.from_file(temp_output)
            sound = sound.speedup(playback_speed=speed)
            sound.export(output_path, format="mp3")
            os.remove(temp_output)  # Remove the temporary file
        else:
            os.rename(temp_output, output_path)

        return output_path
    except Exception as e:
        raise Exception(f"Error converting text to audio: {e}")

def concatenate_audio_files(audio_files, output_path):
    try:
        combined = AudioSegment.empty()
        for file in audio_files:
            audio = AudioSegment.from_file(file)
            combined += audio
        combined.export(output_path, format="mp3")
    except Exception as e:
        raise Exception(f"Error concatenating audio files: {e}")

def register_fonts():
    font_dir = os.path.join(os.path.dirname(__file__), 'fonts')
    pdfmetrics.registerFont(TTFont('NotoSans', os.path.join(font_dir, 'NotoSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('NotoSansJP', os.path.join(font_dir, 'NotoSansJP-Regular.otf')))
    addMapping('NotoSans', 0, 0, 'NotoSans')
    addMapping('NotoSansJP', 0, 0, 'NotoSansJP')

def create_translated_pdf(text, output_path, language_code='en'):
    try:
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        y = height - 50  # Start from top
        
        # Use default Helvetica font
        c.setFont("Helvetica", 11)
        
        # Split text into lines for better handling
        lines = text.split('\n')
        for line in lines:
            # Basic word wrapping
            words = line.split()
            current_line = []
            
            for word in words:
                current_line.append(word)
                line_width = c.stringWidth(' '.join(current_line), "Helvetica", 11)
                
                if line_width > width - 100:
                    # Remove last word and print line
                    current_line.pop()
                    if current_line:
                        c.drawString(50, y, ' '.join(current_line))
                        y -= 20
                    current_line = [word]
                
                # Check if we need a new page
                if y < 50:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = height - 50
            
            # Print remaining words in the line
            if current_line:
                c.drawString(50, y, ' '.join(current_line))
                y -= 20
        
        c.save()
        return output_path
        
    except Exception as e:
        print(f"PDF Creation Error: {str(e)}")  # Add debug logging
        raise Exception(f"Error creating PDF: {str(e)}")

def process_pdf(filename, file_path, language_code, tld, speed, task_id, output_format="audio"):
    try:
        logger.info(f"Starting processing for task {task_id}")
        if not os.path.exists('output'):
            os.makedirs('output')
        if not os.path.exists('temp'):
            os.makedirs('temp')

        # Initialize progress
        progress_dict[task_id] = {'status': 'Processing', 'progress': 0}

        # Extract text chunks
        progress_dict[task_id]['status'] = 'Extracting text from PDF...'
        text_chunks = extract_text_chunks_from_pdf(file_path)
        total_chunks = len(text_chunks)

        if total_chunks == 0:
            raise Exception("No text could be extracted from the PDF")

        # Initialize the translator
        translator = Translator()
        
        # Process chunks in smaller batches
        batch_size = 10
        audio_chunks = []
        translated_text = []  # Store all translated text
        
        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch = text_chunks[batch_start:batch_end]
            
            for i, chunk in enumerate(batch):
                overall_progress = int(((batch_start + i) / total_chunks) * 100)
                progress_dict[task_id]['progress'] = overall_progress
                progress_dict[task_id]['status'] = f'Processing chunk {batch_start + i + 1} of {total_chunks}...'

                try:
                    translated_chunk = translator.translate(chunk, dest=language_code).text
                    translated_text.append(translated_chunk)  # Store translated text
                    
                    if output_format in ["audio", "both"]:
                        # Convert the translated chunk to audio
                        chunk_filename = f"{task_id}_chunk_{batch_start + i}.mp3"
                        audio_chunk_path = convert_text_to_audio(
                            translated_chunk,
                            chunk_filename,
                            language_code,
                            speed,
                            tld,
                        )
                        audio_chunks.append(audio_chunk_path)

                except Exception as e:
                    logger.error(f"Error processing chunk {batch_start + i}: {str(e)}")
                    continue

            # Free up memory after each batch
            import gc
            gc.collect()

        # Handle PDF creation if requested
        if output_format in ["pdf", "both"]:
            pdf_filename = filename.replace(".pdf", f"_translated_{task_id}.pdf")
            pdf_path = os.path.join("output", pdf_filename)
            create_translated_pdf('\n'.join(translated_text), pdf_path, language_code)
            progress_dict[task_id]['pdf_file'] = pdf_path

        # Handle audio if requested
        if output_format in ["audio", "both"]:
            if audio_chunks:
                output_filename = filename.replace(".pdf", f"_{task_id}.mp3")
                final_audio_file = os.path.join("output", output_filename)
                concatenate_audio_files(audio_chunks, final_audio_file)
                progress_dict[task_id]['audio_file'] = final_audio_file

        # Clean up
        for audio_file in audio_chunks:
            try:
                os.remove(audio_file)
            except:
                pass
        try:
            os.remove(file_path)
        except:
            pass

        progress_dict[task_id]['progress'] = 100
        progress_dict[task_id]['status'] = 'Completed'

    except Exception as e:
        logger.error(f"Error in process_pdf: {str(e)}")
        progress_dict[task_id]['status'] = 'Error'
        progress_dict[task_id]['error'] = str(e)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/", methods=["POST"])
def process_file():
    try:
        if "pdf_file" not in request.files:
            return jsonify({"error": "No file part in the request"}), 400
            
        file = request.files["pdf_file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
            
        if file and file.filename.endswith(".pdf"):
            # Get voice and output format
            voice = request.form.get("voice", "en")
            output_format = request.form.get("output_format", "audio")
            
            # Enforce audio-only for Asian languages
            if voice in ['ja', 'zh-CN'] and output_format != 'audio':
                return jsonify({"error": "Only audio conversion is available for Chinese and Japanese"}), 400
            
            # Rest of your existing code...
            task_id = str(uuid.uuid4())
            file_path = os.path.join('uploads', f"{task_id}_{file.filename}")
            file.save(file_path)
            
            speed = float(request.form.get("speed", "1.0"))
            lang_settings = language_map.get(voice, {"lang": "en", "tld": "com"})
            
            thread = threading.Thread(
                target=process_pdf,
                args=(file.filename, file_path, lang_settings["lang"], 
                      lang_settings["tld"], speed, task_id, output_format)
            )
            thread.start()
            
            return jsonify({"task_id": task_id}), 202
            
        return jsonify({"error": "Invalid file type"}), 400
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/progress/<task_id>')
def progress(task_id):
    if task_id in progress_dict:
        return jsonify(progress_dict[task_id])
    else:
        return jsonify({'status': 'Unknown Task'}), 404

@app.route('/download/<task_id>')
def download(task_id):
    if task_id in progress_dict:
        if progress_dict[task_id]['status'] == 'Completed':
            output_format = request.args.get('format', 'audio')
            
            if output_format == 'pdf' and 'pdf_file' in progress_dict[task_id]:
                return send_file(progress_dict[task_id]['pdf_file'], as_attachment=True)
            elif output_format == 'audio' and 'audio_file' in progress_dict[task_id]:
                return send_file(progress_dict[task_id]['audio_file'], as_attachment=True)
            else:
                return jsonify({'error': 'Requested format not available'}), 400
                
        elif progress_dict[task_id]['status'] == 'Error':
            return jsonify({'error': progress_dict[task_id]['error']}), 500
        else:
            return jsonify({'status': progress_dict[task_id]['status']}), 202
    else:
        return jsonify({'error': 'Invalid Task ID'}), 404

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
