from flask import Flask, render_template, request, send_file, jsonify
from PyPDF2 import PdfReader
from gtts import gTTS
from pydub import AudioSegment
import os
from googletrans import Translator
import threading
import uuid

app = Flask(__name__)

# Global dictionary to store progress information
progress_dict = {}

# Mapping language codes and TLDs for accents
language_map = {
    "en": {"lang": "en", "tld": "com"},
    "en-uk": {"lang": "en", "tld": "co.uk"},
    "en-au": {"lang": "en", "tld": "com.au"},
    "es": {"lang": "es", "tld": "com"},
    "fr": {"lang": "fr", "tld": "com"},
    "de": {"lang": "de", "tld": "com"},
}

def extract_text_chunks_from_pdf(pdf_path, max_chunk_length=2000):
    try:
        reader = PdfReader(pdf_path)
        chunks = []
        current_chunk = ''
        for page in reader.pages:
            page_text = page.extract_text()
            if not page_text:
                continue
            words = page_text.split()
            for word in words:
                if len(current_chunk) + len(word) + 1 > max_chunk_length:
                    chunks.append(current_chunk)
                    current_chunk = word
                else:
                    if current_chunk:
                        current_chunk += ' ' + word
                    else:
                        current_chunk = word
        if current_chunk:
            chunks.append(current_chunk)
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

def process_pdf(filename, file_path, language_code, tld, speed, task_id):
    try:
        if not os.path.exists('output'):
            os.makedirs('output')
        if not os.path.exists('temp'):
            os.makedirs('temp')

        # Initialize progress
        progress_dict[task_id] = {'status': 'Processing', 'progress': 0}

        # Extract text chunks
        text_chunks = extract_text_chunks_from_pdf(file_path)
        total_chunks = len(text_chunks)

        # Initialize the translator
        translator = Translator()

        # List to store audio chunks
        audio_chunks = []

        for i, chunk in enumerate(text_chunks):
            # Update progress
            progress_dict[task_id]['progress'] = int((i / total_chunks) * 100)

            # Translate the chunk
            translated_chunk = translator.translate(chunk, dest=language_code).text

            # Convert the translated chunk to audio
            chunk_filename = f"{task_id}_chunk_{i}.mp3"
            audio_chunk_path = convert_text_to_audio(
                translated_chunk,
                chunk_filename,
                language_code,
                speed,
                tld,
            )
            audio_chunks.append(audio_chunk_path)

        # Concatenate all audio chunks into a final audio file
        output_filename = filename.replace(".pdf", f"_{task_id}.mp3")
        final_audio_file = os.path.join("output", output_filename)
        concatenate_audio_files(audio_chunks, final_audio_file)

        # Remove temporary audio chunk files
        for audio_file in audio_chunks:
            os.remove(audio_file)

        # Clean up uploads and temp directories
        os.remove(file_path)

        # Update progress to indicate completion
        progress_dict[task_id]['progress'] = 100
        progress_dict[task_id]['status'] = 'Completed'
        progress_dict[task_id]['file'] = final_audio_file
    except Exception as e:
        progress_dict[task_id]['status'] = 'Error'
        progress_dict[task_id]['error'] = str(e)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            if "pdf_file" not in request.files:
                return jsonify({"error": "No file part in the request"}), 400
            file = request.files["pdf_file"]
            if file.filename == "":
                return jsonify({"error": "No selected file"}), 400
            if file and file.filename.endswith(".pdf"):
                # Generate a unique ID for this task
                task_id = str(uuid.uuid4())

                # Save the file
                if not os.path.exists('uploads'):
                    os.makedirs('uploads')
                file_path = os.path.join("uploads", f"{task_id}_{file.filename}")
                file.save(file_path)

                # Get the selected voice (language)
                voice = request.form.get("voice", "en")
                language_info = language_map.get(voice, {"lang": "en", "tld": "com"})
                language_code = language_info['lang']
                tld = language_info['tld']

                # Get the selected speed
                speed = float(request.form.get("speed", 1.0))

                # Start background thread to process the file
                thread = threading.Thread(target=process_pdf, args=(file.filename, file_path, language_code, tld, speed, task_id))
                thread.start()

                # Return the task ID to the client
                return jsonify({"task_id": task_id})
            else:
                return jsonify({"error": "Invalid file type. Only PDFs are allowed."}), 400
        except Exception as e:
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    return render_template("index.html")

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
            file_path = progress_dict[task_id]['file']
            return send_file(file_path, as_attachment=True)
        elif progress_dict[task_id]['status'] == 'Error':
            return jsonify({'error': progress_dict[task_id]['error']}), 500
        else:
            return jsonify({'status': progress_dict[task_id]['status']}), 202
    else:
        return jsonify({'error': 'Invalid Task ID'}), 404

if __name__ == "__main__":
    app.run(debug=True)
