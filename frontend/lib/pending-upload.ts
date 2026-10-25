// Hands a chosen photo from the "New design" dialog to the workspace page that opens next.

const pending = new Map<string, File>();

export function setPendingUpload(designId: string, file: File) {
  pending.set(designId, file);
}

export function takePendingUpload(designId: string): File | null {
  const f = pending.get(designId) ?? null;
  pending.delete(designId);
  return f;
}
