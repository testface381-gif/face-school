const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const startBtn = document.getElementById('startBtn');
const captureBtn = document.getElementById('captureBtn');
const result = document.getElementById('result');
const cameraSelect = document.getElementById('cameraSelect');
let stream = null;

const CAMERA_STORAGE_KEY = 'schoolFaceAttendancePreferredCameraId';

function showResult(ok, message){
  result.className = ok ? 'result ok' : 'result bad';
  result.textContent = message;
}

function sleep(ms){
  return new Promise(resolve => setTimeout(resolve, ms));
}

function stopCurrentStream(){
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
    stream = null;
  }
}

function scoreCamera(device){
  const label = (device.label || '').toLowerCase();
  let score = 0;

  // Prefer external/USB webcams.
  if (label.includes('usb')) score += 100;
  if (label.includes('external')) score += 90;
  if (label.includes('webcam')) score += 40;
  if (label.includes('logitech')) score += 80;
  if (label.includes('1080')) score += 25;
  if (label.includes('hd')) score += 10;

  // Avoid common built-in camera labels.
  if (label.includes('integrated')) score -= 80;
  if (label.includes('built-in')) score -= 80;
  if (label.includes('internal')) score -= 80;
  if (label.includes('facetime')) score -= 80;
  if (label.includes('hp')) score -= 20;

  return score;
}

async function getVideoDevices(){
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter(d => d.kind === 'videoinput');
}

async function populateCameraList(){
  try {
    // Browser hides camera names until permission is granted. This temporary stream unlocks labels.
    const tempStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    tempStream.getTracks().forEach(track => track.stop());

    const cameras = await getVideoDevices();
    const savedId = localStorage.getItem(CAMERA_STORAGE_KEY) || '';
    const sorted = [...cameras].sort((a, b) => scoreCamera(b) - scoreCamera(a));

    cameraSelect.innerHTML = '<option value="">Auto-select best camera</option>';
    sorted.forEach((camera, index) => {
      const option = document.createElement('option');
      option.value = camera.deviceId;
      option.textContent = camera.label || `Camera ${index + 1}`;
      cameraSelect.appendChild(option);
    });

    if (savedId && sorted.some(c => c.deviceId === savedId)) {
      cameraSelect.value = savedId;
    } else if (sorted.length > 0) {
      // Auto-select best-scored camera. This usually picks USB camera when connected.
      cameraSelect.value = sorted[0].deviceId;
      localStorage.setItem(CAMERA_STORAGE_KEY, sorted[0].deviceId);
    }
  } catch (error) {
    // If permission is not granted yet, the Start button will ask again.
  }
}

async function startCamera(){
  stopCurrentStream();

  let deviceId = cameraSelect.value || localStorage.getItem(CAMERA_STORAGE_KEY) || '';
  let videoConstraints;

  if (deviceId) {
    videoConstraints = {
      deviceId: { exact: deviceId },
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 30 }
    };
  } else {
    videoConstraints = {
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 30 }
    };
  }

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: videoConstraints,
      audio: false
    });
    video.srcObject = stream;
    captureBtn.disabled = false;

    const track = stream.getVideoTracks()[0];
    const settings = track.getSettings ? track.getSettings() : {};
    if (settings.deviceId) {
      localStorage.setItem(CAMERA_STORAGE_KEY, settings.deviceId);
      cameraSelect.value = settings.deviceId;
    }

    showResult(true, 'Camera started. If this is not the USB camera, choose it from Camera source and press Start Camera again.');
  } catch (error) {
    // If exact saved device is unavailable, fall back to any camera.
    if (deviceId) {
      localStorage.removeItem(CAMERA_STORAGE_KEY);
      cameraSelect.value = '';
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
        audio: false
      });
      video.srcObject = stream;
      captureBtn.disabled = false;
      showResult(true, 'Saved camera was not available. Started another camera. Choose USB camera from the list if needed.');
    } else {
      showResult(false, 'Camera permission failed. Please allow camera access and use HTTPS.');
    }
  }
}

function captureFrame(){
  // Keep upload small and stable for Railway. USB cameras can send very large frames.
  const sourceWidth = video.videoWidth || 640;
  const sourceHeight = video.videoHeight || 480;
  const maxWidth = 640;
  const scale = Math.min(1, maxWidth / sourceWidth);
  canvas.width = Math.round(sourceWidth * scale);
  canvas.height = Math.round(sourceHeight * scale);
  const context = canvas.getContext('2d');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.72);
}

cameraSelect.addEventListener('change', () => {
  if (cameraSelect.value) {
    localStorage.setItem(CAMERA_STORAGE_KEY, cameraSelect.value);
  } else {
    localStorage.removeItem(CAMERA_STORAGE_KEY);
  }
});

startBtn.addEventListener('click', async () => {
  try {
    await populateCameraList();
    await startCamera();
  } catch (error) {
    showResult(false, 'Camera permission failed. Please allow camera access and select the USB camera.');
  }
});

captureBtn.addEventListener('click', async () => {
  if (!stream) return;
  captureBtn.disabled = true;
  showResult(true, 'Processing secure face checks. Please keep looking at the camera...');

  const images = [];
  try {
    for (let i = 0; i < 3; i++) {
      images.push(captureFrame());
      await sleep(250);
    }

    const response = await fetch('/api/attendance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: captureBtn.dataset.action, images })
    });
    const data = await response.json();
    showResult(Boolean(data.ok), data.message || 'Unknown response.');
  } catch (error) {
    showResult(false, 'Server error while processing attendance.');
  } finally {
    captureBtn.disabled = false;
  }
});

// Load camera list when the page opens. If browser blocks labels before permission,
// the list will be refreshed again when Start Camera is clicked.
populateCameraList();
