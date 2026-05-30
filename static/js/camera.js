const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const startBtn = document.getElementById('startBtn');
const captureBtn = document.getElementById('captureBtn');
const result = document.getElementById('result');
let stream = null;

function showResult(ok, message){
  result.className = ok ? 'result ok' : 'result bad';
  result.textContent = message;
}

startBtn.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    video.srcObject = stream;
    captureBtn.disabled = false;
    showResult(true, 'Camera started. Look at the camera and press Verify Face.');
  } catch (error) {
    showResult(false, 'Camera permission failed. Please allow camera access and use HTTPS.');
  }
});

captureBtn.addEventListener('click', async () => {
  if (!stream) return;
  captureBtn.disabled = true;
  showResult(true, 'Processing face. Please wait...');
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const context = canvas.getContext('2d');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const image = canvas.toDataURL('image/jpeg', 0.9);
  try {
    const response = await fetch('/api/attendance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: captureBtn.dataset.action, image })
    });
    const data = await response.json();
    showResult(Boolean(data.ok), data.message || 'Unknown response.');
  } catch (error) {
    showResult(false, 'Server error while processing attendance.');
  } finally {
    captureBtn.disabled = false;
  }
});
