import api from "@/lib/api";

// Media tags/ordinary links cannot attach the app-session header in an embedded
// preview. Use the same authenticated (and, when needed, tunneled) API transport.
export async function mediaBlob(path, signal) {
  if (typeof path !== "string" || !path.startsWith("/api/") || path.startsWith("//")) {
    throw new Error("Invalid media path");
  }
  try {
    const { data } = await api.get(path.slice(4), { responseType: "blob", signal, timeout: 120000 });
    if (!(data instanceof Blob) || !data.size) throw new Error("The media file is empty");
    return data;
  } catch (error) {
    // Axios also returns error JSON as a Blob for this responseType. Recover
    // the useful missing-file/login message rather than displaying "404".
    if (error?.response?.data instanceof Blob) {
      try {
        const detail = JSON.parse(await error.response.data.text());
        error.response.data = detail;
        if (typeof detail.detail === "string") error.message = detail.detail;
      } catch { /* Preserve the original network error. */ }
    }
    throw error;
  }
}

export async function mediaObjectUrl(path, signal) {
  return URL.createObjectURL(await mediaBlob(path, signal));
}

// A separate, short-lived URL prevents closing the player (or switching shows)
// from revoking the URL used by an in-progress download. No new tab or authless
// redirect: this click starts a real MP4 download with the intended filename.
export function saveMediaBlob(blob, filename) {
  if (!(blob instanceof Blob) || !blob.size) throw new Error("The media file isn't ready yet");
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
