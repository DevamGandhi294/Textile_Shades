# Colour outline scripts (research prototypes)

None of these change the app yet. They are standalone scripts, not edits to `layer_pipeline.py`.

Install: `pip install opencv-python-headless numpy vtracer`

## Main flow (use these two)
1. `colour_black_outlines.py ORIGINAL.png BLACK_OUTLINE.png OUT_DIR`
   Black outline from ChatGPT + original design -> one transparent PNG per colour (+ preview.png).
2. `layers_to_svg.py OUT_DIR SVG_DIR`
   Every PNG layer -> sharp vector SVG layer (+ all_layers.svg).

Settings at the top of colour_black_outlines.py: SAME (how close shades merge), MAX_LAYERS.

## Earlier experiments
- `split_by_colour.py IMAGE OUT_DIR`: split a coloured-outline image by its own colours, pixels untouched.
- `sharpen_layers.py LAYER_DIR OUT_DIR`: those layers -> solid-colour vector SVGs.
- `outline_from_colours.py PHOTO OUT.png`: outlines straight from a photo's colours, no AI.
