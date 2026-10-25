"""Export MangaLineExtraction (erika.pth) to ONNX and check it matches PyTorch.

    git clone https://github.com/ljsabc/MangaLineExtraction_PyTorch mle
    (download erika.pth from that repo's Releases page)
    pip install torch onnx onnxruntime opencv-python
    python tools/export_onnx.py --repo mle --weights erika.pth --out models/manga_line_extraction.onnx

Input : float32 [1, 1, H, W], grayscale 0..255, H and W multiples of 16 (any size)
Output: float32 [1, 1, H, W], 0 = line, 255 = paper (clip to 0..255)
"""
import argparse, sys, time
import numpy as np, torch, onnxruntime as ort

ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="mle", help="folder of the cloned MangaLineExtraction_PyTorch repo")
ap.add_argument("--weights", default="erika.pth")
ap.add_argument("--out", default="manga_line_extraction.onnx")
ap.add_argument("--test", help="optional grayscale image to compare PyTorch vs ONNX")
args = ap.parse_args()

sys.path.insert(0, args.repo)
from model_torch import res_skip

model = res_skip()
model.load_state_dict(torch.load(args.weights, map_location="cpu"))
model.eval()

dummy = torch.full((1, 1, 512, 512), 255.0)
torch.onnx.export(
    model, dummy, args.out,
    input_names=["image"], output_names=["lines"],
    dynamic_axes={"image": {2: "height", 3: "width"}, "lines": {2: "height", 3: "width"}},
    opset_version=17, dynamo=False,
)
print("exported")

# check: same result as PyTorch on a real image, at a size different from the export size
if not args.test:
    sys.exit(0)

import cv2
img = cv2.imread(args.test, cv2.IMREAD_GRAYSCALE)
h, w = img.shape
H, W = int(np.ceil(h / 16)) * 16, int(np.ceil(w / 16)) * 16
x = np.full((1, 1, H, W), 255, np.float32)
x[0, 0, :h, :w] = img

t = time.time()
with torch.no_grad():
    ref = model(torch.from_numpy(x)).numpy()
t_torch = time.time() - t

sess = ort.InferenceSession(args.out, providers=["CPUExecutionProvider"])
t = time.time()
out = sess.run(None, {"image": x})[0]
t_onnx = time.time() - t

diff = np.abs(np.clip(out, 0, 255) - np.clip(ref, 0, 255))
print(f"size {W}x{H} | PyTorch {t_torch:.1f} s | ONNX Runtime {t_onnx:.1f} s")
print(f"max pixel difference {diff.max():.3f} (of 255), mean {diff.mean():.5f}")
print("same B&W result on", f"{((out < 128) == (ref < 128)).mean() * 100:.4f}% of pixels")
