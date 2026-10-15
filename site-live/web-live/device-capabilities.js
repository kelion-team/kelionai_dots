// Browser-side hardware capability inspector. No telemetry, storage, or permission prompts.
export async function inspectDevice({ nav = navigator, screenInfo = screen, win = window, doc = document } = {}) {
  const media = nav.mediaDevices;
  const readPermission = async name => {
    if (!nav.permissions?.query) return 'unknown';
    try { return (await nav.permissions.query({ name })).state; }
    catch { return 'unknown'; }
  };
  let devices = [];
  if (media?.enumerateDevices) {
    try { devices = await media.enumerateDevices(); } catch { devices = []; }
  }
  const count = kind => devices.filter(d => d.kind === kind).length;
  const observed = kind => {
    if (!media?.enumerateDevices) return 'unsupported';
    return count(kind) ? 'detected' : 'not-detected-or-hidden';
  };
  const gpsPermission = nav.geolocation ? await readPermission('geolocation') : 'unsupported';
  return {
    observed_at: new Date().toISOString(),
    origin: 'browser-local',
    display: {
      viewport_css_px: [win.innerWidth, win.innerHeight],
      screen_css_px: [screenInfo.width, screenInfo.height],
      available_screen_css_px: [screenInfo.availWidth, screenInfo.availHeight],
      device_pixel_ratio: win.devicePixelRatio ?? null,
      orientation: screenInfo.orientation?.type ?? null,
      touch_points: Number.isFinite(nav.maxTouchPoints) ? nav.maxTouchPoints : null
    },
    camera: { state: observed('videoinput'), permission: await readPermission('camera') },
    microphone: { state: observed('audioinput'), permission: await readPermission('microphone') },
    speaker: { state: observed('audiooutput'), web_audio: Boolean(win.AudioContext || win.webkitAudioContext) },
    gps: { api: Boolean(nav.geolocation), permission: gpsPermission },
    browser_audio_capture: Boolean(media?.getUserMedia),
    browser_audio_playback: Boolean(win.Audio),
    // Hardware models and native device dimensions are not reliably exposed by browsers.
    physical_dimensions: 'not-exposed-by-browser'
  };
}
