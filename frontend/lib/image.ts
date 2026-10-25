// Browser-side image helpers for the workspace.

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Could not read this image."));
    img.src = src;
  });
}

/**
 * A copy of the raw photo small enough to keep with the design (max 2400 px, the backend's
 * working size, so uploading this copy again gives the same result).
 */
export async function storableCopy(file: File, maxSide = 2400): Promise<{ url: string; width: number; height: number }> {
  const src = URL.createObjectURL(file);
  try {
    const img = await loadImage(src);
    const f = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.naturalWidth * f);
    canvas.height = Math.round(img.naturalHeight * f);
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return { url: canvas.toDataURL("image/jpeg", 0.9), width: img.naturalWidth, height: img.naturalHeight };
  } finally {
    URL.revokeObjectURL(src);
  }
}

/** Turns a saved image (any URL the browser can draw, SVG included) into a PNG file to upload. */
export async function urlToUploadFile(url: string, name: string, minSide = 1600): Promise<File> {
  const img = await loadImage(url);
  const w = img.naturalWidth || 1200;
  const h = img.naturalHeight || 900;
  const f = Math.max(1, minSide / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * f);
  canvas.height = Math.round(h * f);
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not prepare the image."))), "image/png"),
  );
  return new File([blob], `${name.replace(/[^\w-]+/g, "_").slice(0, 40) || "sketch"}.png`, { type: "image/png" });
}

export async function imageSize(url: string): Promise<{ width: number; height: number }> {
  const img = await loadImage(url);
  return { width: img.naturalWidth, height: img.naturalHeight };
}
