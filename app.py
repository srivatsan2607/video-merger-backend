from flask import Flask, request, jsonify, send_from_directory
import jwt
import datetime
import os
import ffmpeg
from celery import Celery
import os
from flask_cors import CORS
import logging


logger = logging.getLogger(__name__)


UPLOAD_FOLDER = "uploads"
MERGED_FOLDER = "merged_videos"

# Create necessary directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MERGED_FOLDER, exist_ok=True)


def make_celery(app):
    celery = Celery(
        "tasks",
        backend=app.config["CELERY_RESULT_BACKEND"],
        broker=app.config["CELERY_BROKER_URL"],
    )
    celery.conf.update(app.config)
    return celery


app = Flask(__name__)
CORS(app)
app.config.update(
    CELERY_BROKER_URL="redis://localhost:6379/0",
    CELERY_RESULT_BACKEND="redis://localhost:6379/0",
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    MERGED_FOLDER=MERGED_FOLDER,
)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MERGED_FOLDER"] = MERGED_FOLDER
print(f"UPLOAD_FOLDER is set to: {app.config['UPLOAD_FOLDER']}")

celeryApp = make_celery(app)


# Secret key for JWT encoding/decoding
app.config["SECRET_KEY"] = "KIBIBIT_TEST_SECRET"

UPLOAD_FOLDER = "uploads"
MERGED_FOLDER = "merged_videos"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(MERGED_FOLDER):
    os.makedirs(MERGED_FOLDER)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MERGED_FOLDER"] = MERGED_FOLDER

# Dummy user data for authentication
users = {"testuser": "password123"}


def verify_token(token):
    try:
        decoded = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        return None  # Token has expired
    except jwt.InvalidTokenError:
        return None  # Token is invalid


@app.route("/login", methods=["POST"])
def login():
    print(request.json)
    auth_data = request.json
    if auth_data == None:
        return jsonify({"message": "Username and password required"}), 400
    username = auth_data.get("username")
    password = auth_data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    # Check user credentials
    if users.get(username) == None or users.get(username) != password:
        return jsonify({"message": "Invalid credentials"}), 401

    # Generate JWT token
    token = jwt.encode(
        {
            "username": username,
            "exp": datetime.datetime.now() + datetime.timedelta(hours=1),
        },
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )

    return jsonify({"token": token})


@app.route("/upload", methods=["POST"])
def upload_videos():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"message": "Authorization token is missing"}), 401

    token = auth_header.split(" ")[1]
    user_data = verify_token(token)
    if not user_data:
        return jsonify({"message": "Invalid or expired token"}), 401

    if not request.files:
        return jsonify({"message": "No files uploaded"}), 400

    if not request.files:
        return jsonify({"message": "No files uploaded"}), 400

    uploaded_files = request.files
    saved_files = []

    for key in uploaded_files:
        file = uploaded_files[key]
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(file_path)
        saved_files.append(file.filename)

    return jsonify({"message": "Videos uploaded successfully", "files": saved_files})


@app.route("/videos", methods=["GET"])
def list_videos():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"message": "Authorization token is missing"}), 401

    token = auth_header.split(" ")[1]
    user_data = verify_token(token)
    if not user_data:
        return jsonify({"message": "Invalid or expired token"}), 401

    files = os.listdir(app.config["UPLOAD_FOLDER"])
    videos = []

    for file in files:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file)
        if os.path.isfile(file_path):
            file_details = {
                "name": file,
                "url": f"http://127.0.0.1:5000/videos/{file}",
                "size": os.path.getsize(file_path),  # File size in bytes
            }
            videos.append(file_details)

    return jsonify({"videos": videos})


@app.route("/videos/merged", methods=["GET"])
def list_merged_videos():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"message": "Authorization token is missing"}), 401

    token = auth_header.split(" ")[1]
    user_data = verify_token(token)
    if not user_data:
        return jsonify({"message": "Invalid or expired token"}), 401

    files = os.listdir(app.config["MERGED_FOLDER"])
    videos = []

    for file in files:
        file_path = os.path.join(app.config["MERGED_FOLDER"], file)
        if os.path.isfile(file_path):
            file_details = {
                "name": file,
                "url": f"http://127.0.0.1:5000/videos/merged/{file}",
                "size": os.path.getsize(file_path),  # File size in bytes
            }
            videos.append(file_details)

    return jsonify({"videos": videos})


@app.route("/videos/<filename>", methods=["GET"])
def serve_video(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/videos/merged/<filename>", methods=["GET"])
def serve_merged_video(filename):
    return send_from_directory(app.config["MERGED_FOLDER"], filename)


@celeryApp.task(bind=True, track_started=True, name="app.merge_videos")
def merge_videos(self, file_paths, output_filename):
    concat_file = f"concat_list_{self.request.id}.txt"
    output_path = os.path.join(app.config["MERGED_FOLDER"], output_filename)

    try:
        # Write the file paths to the concat file
        with open(concat_file, "w") as f:
            for file in file_paths:
                f.write(f"file '{os.path.abspath(file)}'\n")

        logger.info(f"Starting merge for {file_paths} into {output_path}")
        ffmpeg.input(concat_file, format="concat", safe=0).output(output_path).run()
        logger.info("Merge completed!")

        return {"status": "completed", "file": output_path}
    except ffmpeg.Error as e:
        logger.error(f"FFMPEG error: {e.stderr.decode('utf-8')}")
        raise self.retry(exc=e)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise self.retry(exc=e)
    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)


@app.route("/merge", methods=["POST"])
def merge_files():
    files = request.json.get("files")
    file_paths = []
    for file in files:
        file_paths.append(os.path.join(app.config["UPLOAD_FOLDER"], file))

    print(file_paths)

    output_filename = (
        f"merged_video_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
    )
    print("About to start merging")

    # Start Celery task to merge the videos
    merge_task = merge_videos.apply_async(args=[file_paths, output_filename])

    # Return task ID to monitor progress
    return jsonify({"task_id": merge_task.id, "message": "Video merging started"}), 202


@app.route("/status/<task_id>", methods=["GET"])
def get_status(task_id):
    task = merge_videos.AsyncResult(task_id)
    print(task)
    print(task.state)
    if task.state == "PENDING":
        response = {"status": "Task is pending...", "state": "PENDING"}
    elif task.state == "STARTED":
        response = {"status": "Merging in progress...", "state": "STARTED"}
    elif task.state == "SUCCESS":
        response = {
            "status": "Task completed",
            "result": task.result,
            "state": "SUCCESS",
        }
    elif task.state == "FAILURE":
        response = {
            "status": "Task failed",
            "error": str(task.info),
            "state": "FAILURE",
        }

    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True)
