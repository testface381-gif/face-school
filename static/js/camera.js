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

function sleep(ms){
  return new Promise(resolve => setTimeout(resolve, ms));
}

function captureFrame(){
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const context = canvas.getContext('2d');
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.92);
}

startBtn.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false
    });
    video.srcObject = stream;
    captureBtn.disabled = false;
    showResult(true, 'Camera started. Look directly at the camera. The system will check several frames for higher accuracy.');
  } catch (error) {
    showResult(false, 'Camera permission failed. Please allow camera access and use HTTPS.');
  }
});

captureBtn.addEventListener('click', async () => {
  if (!stream) return;
  captureBtn.disabled = true;
  showResult(true, 'Processing multiple face checks. Please keep looking at the camera...');

  const images = [];
  try {
    for (let i = 0; i < 5; i++) {
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
