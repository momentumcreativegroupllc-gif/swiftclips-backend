from app.services.storage import upload_video_bytes

def main():
    file_path = "requirements.txt"

    with open(file_path, "rb") as f:
        data = f.read()

    dest_path = "test/requirements.txt"

    url = upload_video_bytes(dest_path, data)
    print("Uploaded to:", url)

if __name__ == "__main__":
    main()
