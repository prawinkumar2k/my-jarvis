/**
 * The microphone chosen in the header selector, applied to browser capture.
 *
 * The backend saves the device by its Windows name; the browser has its own
 * device ids, so the choice is matched by label. `ideal` (not `exact`) keeps
 * capture working on the default mic if the chosen one is unplugged.
 */
let preferredName = '';

// Windows drops characters like (R) from device names; compare letters and digits only.
const normalize = (text) => String(text || '').toLowerCase().replace(/[^a-z0-9]/g, '');

export function setPreferredMicName(name) {
    preferredName = String(name || '').trim();
}

export async function audioConstraints(base) {
    const audio = { ...(base || {}) };
    if (!preferredName) return { audio };
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const wanted = normalize(preferredName);
        const match = devices.find((d) => d.kind === 'audioinput' && d.label && normalize(d.label).startsWith(wanted));
        if (match) audio.deviceId = { ideal: match.deviceId };
    } catch (_) { /* enumerateDevices unavailable: use the default mic */ }
    return { audio };
}
