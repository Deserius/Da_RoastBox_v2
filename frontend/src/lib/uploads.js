const ALLOWED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

export function imageError(file) {
  if (!file) return "No image selected.";
  if (file.size > MAX_IMAGE_BYTES) return "Each photo must be 8 MB or smaller.";
  if (file.type && !ALLOWED_TYPES.has(file.type)) return "Use a JPEG, PNG, or WebP photo.";
  return "";
}
