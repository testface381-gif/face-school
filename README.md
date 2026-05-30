# School Face Recognition Attendance - Railway Ready

A clean Flask project for teacher face-recognition attendance.

## Features

- Admin login
- Upload teacher names and multiple face photos
- Teacher Sign In using laptop camera
- Teacher Sign Out using laptop camera
- Face matching using OpenCV LBPH recognizer
- Attendance database with sign-in and sign-out times
- Advanced report filters
- Professional Excel export
- Railway-ready deployment files

## Default Admin Login

Username: `admin`  
Password: `1234`

Change this later for production.

## Important Railway Settings

Use these settings in Railway:

### Start Command

```bash
gunicorn app:app
```

### Python Version

The project already includes:

```text
.python-version
runtime.txt
```

Both force Python 3.11.9.

### Environment Variables

Recommended:

```text
PYTHON_VERSION=3.11.9
SECRET_KEY=change-to-a-long-random-secret
FACE_CONFIDENCE_THRESHOLD=75
```

If you add Railway PostgreSQL, Railway will provide:

```text
DATABASE_URL
```

The app automatically uses it.

## Persistent Teacher Images

By default, teacher images are saved in:

```text
static/uploads/teachers
```

For permanent production use on Railway, add a Railway Volume and set:

```text
UPLOAD_DIR=/data/teachers
```

Then mount the Railway Volume to:

```text
/data
```

Without a persistent volume, uploaded teacher images may disappear after redeploy.

## Deploy to Railway

1. Upload this project to GitHub.
2. Open Railway.
3. Create New Project.
4. Deploy from GitHub repo.
5. Select this repository.
6. Add environment variable:

```text
PYTHON_VERSION=3.11.9
```

7. Set start command:

```bash
gunicorn app:app
```

8. Deploy.
9. Open the generated Railway URL.
10. Login using `admin / 1234`.

## Testing Order

1. Login as admin.
2. Upload one teacher with 3 clear front-face photos.
3. Test Sign In.
4. Test Sign Out.
5. Open Reports.
6. Download Excel.

## Notes for Better Accuracy

- Upload 2 to 5 clear photos per teacher.
- Use front-facing photos.
- Avoid sunglasses, masks, side profiles, dark lighting, or blurry images.
- Teacher should stand in similar lighting during sign-in.

## Production Recommendation

For real school use:

- Use Railway PostgreSQL for attendance records.
- Use Railway Volume for uploaded teacher images.
- Change the default admin password.
- Use a strong SECRET_KEY.
- Use HTTPS only.

## Accuracy Safety Update
This version uses a stricter OpenCV LBPH verification process:
- Default confidence threshold changed to 45. Lower confidence is better.
- Requires at least 3 successful matches from 5 camera frames.
- Rejects blurry, too-dark, or overexposed images.
- Rejects uncertain matches when the best match is too close to the second-best teacher.

Recommended Railway variables:
- `FACE_CONFIDENCE_THRESHOLD=45`
- `FACE_MARGIN_THRESHOLD=12`
- `FACE_REQUIRED_MATCHES=3`

For best results, upload 3–5 clear photos per teacher.

## Low-resolution laptop camera mode - v3

This version is adjusted for weak laptop webcams:

- Face quality/blurry/dark checks are disabled by default.
- The app checks the face content instead of rejecting because the camera is low resolution.
- Face detection is more tolerant using multiple Haar cascades and smaller face size.

Recommended Railway variables:

FACE_SKIP_QUALITY_CHECK=1
FACE_DETECTION_MIN_SIZE=40
FACE_CONFIDENCE_THRESHOLD=45
FACE_MARGIN_THRESHOLD=12
FACE_REQUIRED_MATCHES=3

Only use this optional fallback if the laptop camera still fails to detect faces:

FACE_ALLOW_CENTER_FALLBACK=1

Warning: center fallback may reduce security, so keep it OFF unless needed.

## USB Camera Selection
This version includes a camera source selector on the attendance page. It automatically prefers USB/external cameras when available and remembers the selected camera in the browser. If the laptop camera opens first, select the USB camera from the dropdown and press **Start Camera** again.
