# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.

# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import argparse
import os
import shutil
from collections import defaultdict

import numpy as np
import torch
from PIL import Image
from sam2.build_sam import build_sam2_video_predictor
from tqdm import tqdm


# the PNG palette for DAVIS 2017 dataset
DAVIS_PALETTE = b"\x00\x00\x00\x80\x00\x00\x00\x80\x00\x80\x80\x00\x00\x00\x80\x80\x00\x80\x00\x80\x80\x80\x80\x80@\x00\x00\xc0\x00\x00@\x80\x00\xc0\x80\x00@\x00\x80\xc0\x00\x80@\x80\x80\xc0\x80\x80\x00@\x00\x80@\x00\x00\xc0\x00\x80\xc0\x00\x00@\x80\x80@\x80\x00\xc0\x80\x80\xc0\x80@@\x00\xc0@\x00@\xc0\x00\xc0\xc0\x00@@\x80\xc0@\x80@\xc0\x80\xc0\xc0\x80\x00\x00@\x80\x00@\x00\x80@\x80\x80@\x00\x00\xc0\x80\x00\xc0\x00\x80\xc0\x80\x80\xc0@\x00@\xc0\x00@@\x80@\xc0\x80@@\x00\xc0\xc0\x00\xc0@\x80\xc0\xc0\x80\xc0\x00@@\x80@@\x00\xc0@\x80\xc0@\x00@\xc0\x80@\xc0\x00\xc0\xc0\x80\xc0\xc0@@@\xc0@@@\xc0@\xc0\xc0@@@\xc0\xc0@\xc0@\xc0\xc0\xc0\xc0\xc0 \x00\x00\xa0\x00\x00 \x80\x00\xa0\x80\x00 \x00\x80\xa0\x00\x80 \x80\x80\xa0\x80\x80`\x00\x00\xe0\x00\x00`\x80\x00\xe0\x80\x00`\x00\x80\xe0\x00\x80`\x80\x80\xe0\x80\x80 @\x00\xa0@\x00 \xc0\x00\xa0\xc0\x00 @\x80\xa0@\x80 \xc0\x80\xa0\xc0\x80`@\x00\xe0@\x00`\xc0\x00\xe0\xc0\x00`@\x80\xe0@\x80`\xc0\x80\xe0\xc0\x80 \x00@\xa0\x00@ \x80@\xa0\x80@ \x00\xc0\xa0\x00\xc0 \x80\xc0\xa0\x80\xc0`\x00@\xe0\x00@`\x80@\xe0\x80@`\x00\xc0\xe0\x00\xc0`\x80\xc0\xe0\x80\xc0 @@\xa0@@ \xc0@\xa0\xc0@ @\xc0\xa0@\xc0 \xc0\xc0\xa0\xc0\xc0`@@\xe0@@`\xc0@\xe0\xc0@`@\xc0\xe0@\xc0`\xc0\xc0\xe0\xc0\xc0\x00 \x00\x80 \x00\x00\xa0\x00\x80\xa0\x00\x00 \x80\x80 \x80\x00\xa0\x80\x80\xa0\x80@ \x00\xc0 \x00@\xa0\x00\xc0\xa0\x00@ \x80\xc0 \x80@\xa0\x80\xc0\xa0\x80\x00`\x00\x80`\x00\x00\xe0\x00\x80\xe0\x00\x00`\x80\x80`\x80\x00\xe0\x80\x80\xe0\x80@`\x00\xc0`\x00@\xe0\x00\xc0\xe0\x00@`\x80\xc0`\x80@\xe0\x80\xc0\xe0\x80\x00 @\x80 @\x00\xa0@\x80\xa0@\x00 \xc0\x80 \xc0\x00\xa0\xc0\x80\xa0\xc0@ @\xc0 @@\xa0@\xc0\xa0@@ \xc0\xc0 \xc0@\xa0\xc0\xc0\xa0\xc0\x00`@\x80`@\x00\xe0@\x80\xe0@\x00`\xc0\x80`\xc0\x00\xe0\xc0\x80\xe0\xc0@`@\xc0`@@\xe0@\xc0\xe0@@`\xc0\xc0`\xc0@\xe0\xc0\xc0\xe0\xc0  \x00\xa0 \x00 \xa0\x00\xa0\xa0\x00  \x80\xa0 \x80 \xa0\x80\xa0\xa0\x80` \x00\xe0 \x00`\xa0\x00\xe0\xa0\x00` \x80\xe0 \x80`\xa0\x80\xe0\xa0\x80 `\x00\xa0`\x00 \xe0\x00\xa0\xe0\x00 `\x80\xa0`\x80 \xe0\x80\xa0\xe0\x80``\x00\xe0`\x00`\xe0\x00\xe0\xe0\x00``\x80\xe0`\x80`\xe0\x80\xe0\xe0\x80  @\xa0 @ \xa0@\xa0\xa0@  \xc0\xa0 \xc0 \xa0\xc0\xa0\xa0\xc0` @\xe0 @`\xa0@\xe0\xa0@` \xc0\xe0 \xc0`\xa0\xc0\xe0\xa0\xc0 `@\xa0`@ \xe0@\xa0\xe0@ `\xc0\xa0`\xc0 \xe0\xc0\xa0\xe0\xc0``@\xe0`@`\xe0@\xe0\xe0@``\xc0\xe0`\xc0`\xe0\xc0\xe0\xe0\xc0"


def load_ann_png(path):
    """Load a PNG file as a mask and its palette."""
    mask = Image.open(path)
    palette = mask.getpalette()
    mask = np.array(mask).astype(np.uint8)
    return mask, palette


def save_ann_png(path, mask, palette):
    """Save a mask as a PNG file with the given palette."""
    assert mask.dtype == np.uint8
    assert mask.ndim == 2
    output_mask = Image.fromarray(mask)
    # output_mask.putpalette(palette)
    output_mask.save(path)
    print(f"Saved mask to {path}")


def get_per_obj_mask(mask):
    """Split a mask into per-object masks."""
    object_ids = np.unique(mask)
    object_ids = object_ids[object_ids > 0].tolist()
    per_obj_mask = {object_id: (mask == object_id) for object_id in object_ids}
    return per_obj_mask


def put_per_obj_mask(per_obj_mask, height, width):
    """Combine per-object masks into a single mask."""
    mask = np.zeros((height, width), dtype=np.uint8)
    object_ids = sorted(per_obj_mask)[::-1]
    print(object_ids)
    for object_id in object_ids:
        object_mask = per_obj_mask[object_id]
        object_mask = object_mask.reshape(height, width)
        mask[object_mask] = object_id
    return mask


def load_masks_from_dir(
    input_mask_dir, video_name, frame_name, per_obj_png_file, allow_missing=False
):
    """Load masks from a directory as a dict of per-object masks."""
    if not per_obj_png_file:
        input_mask_path = os.path.join(input_mask_dir, video_name, f"{frame_name}.png")
        if allow_missing and not os.path.exists(input_mask_path):
            return {}, None
        input_mask, input_palette = load_ann_png(input_mask_path)
        per_obj_input_mask = get_per_obj_mask(input_mask)
    else:
        per_obj_input_mask = {}
        input_palette = None
        # each object is a directory in "{object_id:%03d}" format
        for object_name in os.listdir(os.path.join(input_mask_dir, video_name)):
            object_id = int(object_name)
            input_mask_path = os.path.join(
                input_mask_dir, video_name, object_name, f"{frame_name}.png"
            )
            if allow_missing and not os.path.exists(input_mask_path):
                continue
            input_mask, input_palette = load_ann_png(input_mask_path)
            per_obj_input_mask[object_id] = input_mask > 0

    return per_obj_input_mask, input_palette


def save_masks_to_dir(
    output_mask_dir,
    video_name,
    frame_name,
    per_obj_output_mask,
    height,
    width,
    per_obj_png_file,
    output_palette,
):
    """Save masks to a directory as PNG files."""
    print(f"Saving masks for {video_name} - {frame_name}...")
    os.makedirs(os.path.join(output_mask_dir, video_name), exist_ok=True)
    if not per_obj_png_file:
        output_mask = put_per_obj_mask(per_obj_output_mask, height, width)
        output_mask_path = os.path.join(
            output_mask_dir, video_name, f"{frame_name}.png"
        )
        save_ann_png(output_mask_path, output_mask, output_palette)
        print(f"Saved combined mask to {output_mask_path}")
    else:
        for object_id, object_mask in per_obj_output_mask.items():
            object_name = f"{object_id:03d}"
            os.makedirs(
                os.path.join(output_mask_dir, video_name, object_name),
                exist_ok=True,
            )
            output_mask = object_mask.reshape(height, width).astype(np.uint8)
            output_mask_path = os.path.join(
                output_mask_dir, video_name, object_name, f"{frame_name}.png"
            )
            save_ann_png(output_mask_path, output_mask, output_palette)


@torch.inference_mode()
@torch.autocast(device_type="cuda", dtype=torch.bfloat16)
def vos_inference(
    predictor,
    base_video_dir,
    input_mask_dir,
    output_mask_dir,
    video_name,
    score_thresh=0.0,
    use_all_masks=False,
    per_obj_png_file=False,
):
    """Run VOS inference on a single video with the given predictor."""
    # load the video frames and initialize the inference state on this video
    video_dir = os.path.join(base_video_dir, video_name)
    frame_names = [
        os.path.splitext(p)[0]
        for p in os.listdir(video_dir)
        if os.path.splitext(p)[-1] in [".jpg", ".jpeg", ".JPG", ".JPEG", '.png']
    ]
    frame_names.sort(key=lambda p: os.path.splitext(p)[0])
    inference_state = predictor.init_state(
        video_path=video_dir, async_loading_frames=False, offload_video_to_cpu=True
    )
    height = inference_state["video_height"]
    width = inference_state["video_width"]
    input_palette = None

    # fetch mask inputs from input_mask_dir (either only mask for the first frame, or all available masks)
    if not use_all_masks:
        # use only the first video's ground-truth mask as the input mask
        input_frame_inds = [0]
    else:
        # use all mask files available in the input_mask_dir as the input masks
        if not per_obj_png_file:
            input_frame_inds = [
                idx
                for idx, name in enumerate(frame_names)
                if os.path.exists(
                    os.path.join(input_mask_dir, video_name, f"{name}.png")
                )
            ]
        else:
            input_frame_inds = [
                idx
                for object_name in os.listdir(os.path.join(input_mask_dir, video_name))
                for idx, name in enumerate(frame_names)
                if os.path.exists(
                    os.path.join(input_mask_dir, video_name, object_name, f"{name}.png")
                )
            ]
        # check and make sure we got at least one input frame
        if len(input_frame_inds) == 0:
            raise RuntimeError(
                f"In {video_name=}, got no input masks in {input_mask_dir=}. "
                "Please make sure the input masks are available in the correct format."
            )
        input_frame_inds = sorted(set(input_frame_inds))

    # add those input masks to SAM 2 inference state before propagation
    object_ids_set = None
    for input_frame_idx in input_frame_inds:
        try:
            per_obj_input_mask, input_palette = load_masks_from_dir(
                input_mask_dir=input_mask_dir,
                video_name=video_name,
                frame_name=frame_names[input_frame_idx],
                per_obj_png_file=per_obj_png_file,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"In {video_name=}, failed to load input mask for frame {input_frame_idx=}. "
                "Please add the `--track_object_appearing_later_in_video` flag "
                "for VOS datasets that don't have all objects to track appearing "
                "in the first frame (such as LVOS or YouTube-VOS)."
            ) from e
        # get the list of object ids to track from the first input frame
        if object_ids_set is None:
            object_ids_set = set(per_obj_input_mask)
        for object_id, object_mask in per_obj_input_mask.items():
            # check and make sure no new object ids appear only in later frames
            if object_id not in object_ids_set:
                raise RuntimeError(
                    f"In {video_name=}, got a new {object_id=} appearing only in a "
                    f"later {input_frame_idx=} (but not appearing in the first frame). "
                    "Please add the `--track_object_appearing_later_in_video` flag "
                    "for VOS datasets that don't have all objects to track appearing "
                    "in the first frame (such as LVOS or YouTube-VOS)."
                )
            predictor.add_new_mask(
                inference_state=inference_state,
                frame_idx=input_frame_idx,
                obj_id=object_id,
                mask=object_mask,
            )

    # check and make sure we have at least one object to track
    if object_ids_set is None or len(object_ids_set) == 0:
        raise RuntimeError(
            f"In {video_name=}, got no object ids on {input_frame_inds=}. "
            "Please add the `--track_object_appearing_later_in_video` flag "
            "for VOS datasets that don't have all objects to track appearing "
            "in the first frame (such as LVOS or YouTube-VOS)."
        )
    # run propagation throughout the video and collect the results in a dict
    os.makedirs(os.path.join(output_mask_dir, video_name), exist_ok=True)
    output_palette = input_palette or DAVIS_PALETTE
    video_segments = {}  # video_segments contains the per-frame segmentation results
    for out_frame_idx, out_obj_ids, out_mask_logits in predictor.propagate_in_video(
        inference_state
    ):
        per_obj_output_mask = {
            out_obj_id: (out_mask_logits[i] > score_thresh).cpu().numpy()
            for i, out_obj_id in enumerate(out_obj_ids)
        }
        video_segments[out_frame_idx] = per_obj_output_mask

    # write the output masks as palette PNG files to output_mask_dir
    for out_frame_idx, per_obj_output_mask in video_segments.items():
        save_masks_to_dir(
            output_mask_dir=output_mask_dir,
            video_name=video_name,
            frame_name=frame_names[out_frame_idx],
            per_obj_output_mask=per_obj_output_mask,
            height=height,
            width=width,
            per_obj_png_file=per_obj_png_file,
            output_palette=output_palette,
        )

def chunk_files_by_reference(folder_a, folder_b):
    """
    Chunks files in folder_a into subdirectories based on the order of base names in folder_b.
    Files are matched by name only (ignoring extensions).
    Each chunk starts from a reference file in B and ends before the next reference.
    """
    # Get sorted list of files in A and B
    files_a = sorted(os.listdir(folder_a))
    files_b = sorted(os.listdir(folder_b))

    # Map base name (no extension) of files in A to their index
    index_map = {
        os.path.splitext(f)[0]: i
        for i, f in enumerate(files_a)
    }

    # Extract base names from files in B
    base_names_b = [os.path.splitext(f)[0] for f in files_b]

    # Build list of (base_name, index_in_A) tuples, keeping only those that exist in A
    sorted_refs = sorted(
        [(name, index_map[name]) for name in base_names_b if name in index_map],
        key=lambda x: x[1]
    )

    if not sorted_refs:
        print("No matching reference files found in folder A.")
        return

    # Prepare chunk ranges using the sorted indices
    chunk_ranges = []
    print(f"Chunking {len(sorted_refs)} reference files into {len(files_a)} files in '{folder_a}'")

    for i in range(len(sorted_refs)):
        start_idx = sorted_refs[i][1]
        end_idx = sorted_refs[i + 1][1] if i + 1 < len(sorted_refs) else len(files_a)
        chunk_files = files_a[start_idx:end_idx]
        chunk_ranges.append((sorted_refs[i][0], chunk_files))

    # Move files into corresponding subdirectories
    for base_name, chunk in chunk_ranges:
        chunk_dir = os.path.join(folder_a, base_name.split('_')[-1])  # Use trailing index as folder name
        os.makedirs(chunk_dir, exist_ok=True)
        for f in chunk:
            src = os.path.join(folder_a, f)
            dst = os.path.join(chunk_dir, f)
            shutil.move(src, dst)
        print(f"Moved {len(chunk)} files to '{chunk_dir}'")

def flatten_folder(folder_a):
    """
    Move all files from subdirectories in folder_a back to folder_a and remove subdirectories.
    """
    # Iterate over items in A
    for item in os.listdir(folder_a):
        item_path = os.path.join(folder_a, item)
        print(f"Processing item: {item_path}")
        # Skip if not a directory
        if not os.path.isdir(item_path):
            continue

        # Move all files from subdir to A
        for f in os.listdir(item_path):
            src_path = os.path.join(item_path, f)
            dst_path = os.path.join(folder_a, f)

            if os.path.exists(dst_path):
                raise FileExistsError(f"Target file already exists: {dst_path}")

            shutil.move(src_path, dst_path)

        # Remove the now-empty directory
        os.rmdir(item_path)
        print(f"Removed folder: {item_path}")

    print(f"All files have been moved back to {folder_a}")

@torch.inference_mode()
@torch.autocast(device_type="cuda", dtype=torch.bfloat16)
def vos_separate_inference_per_object(
    predictor,
    base_video_dir,
    input_mask_dir,
    output_mask_dir,
    video_name,
    score_thresh=0.0,
    use_all_masks=False,
    per_obj_png_file=False,
    is_lidar=False,
):
    """
    Run VOS inference on a single video with the given predictor.

    Unlike `vos_inference`, this function run inference separately for each object
    in a video, which could be applied to datasets like LVOS or YouTube-VOS that
    don't have all objects to track appearing in the first frame (i.e. some objects
    might appear only later in the video).
    """
    # load the video frames and initialize the inference state on this video
    video_dir = os.path.join(base_video_dir, video_name)
    
    # Run the chunking if it has not already been done
    if all(os.path.isdir(os.path.join(video_dir, subdir)) for subdir in os.listdir(video_dir)):
        print("Chunking has already been done, skipping...")
    else:
        print("Chunking files by reference...")
        chunk_files_by_reference(video_dir, os.path.join(input_mask_dir, video_name))

    try:
        for subdir in os.listdir(video_dir):
            frame_names = [
                os.path.splitext(p)[0]
                for p in os.listdir(os.path.join(video_dir, subdir))
                if os.path.splitext(p)[-1] in [".jpg", ".jpeg", ".JPG", ".JPEG", '.png']
            ]
            frame_names.sort(key=lambda p: os.path.splitext(p)[0])
            inference_state = predictor.init_state(
                video_path=os.path.join(video_dir, subdir), async_loading_frames=False, is_lidar=is_lidar
            )
            height = inference_state["video_height"]
            width = inference_state["video_width"]
            input_palette = None

            # collect all the object ids and their input masks
            inputs_per_object = defaultdict(dict)
            for idx, name in enumerate(frame_names):
                if per_obj_png_file or os.path.exists(
                    os.path.join(input_mask_dir, video_name, f"{name}.png")
                ):
                    per_obj_input_mask, input_palette = load_masks_from_dir(
                        input_mask_dir=input_mask_dir,
                        video_name=video_name,
                        frame_name=frame_names[idx],
                        per_obj_png_file=per_obj_png_file,
                        allow_missing=True,
                    )
                    for object_id, object_mask in per_obj_input_mask.items():
                        # skip empty masks
                        if not np.any(object_mask):
                            continue
                        # if `use_all_masks=False`, we only use the first mask for each object
                        if len(inputs_per_object[object_id]) > 0 and not use_all_masks:
                            continue
                        print(f"adding mask from frame {idx} as input for {object_id=}")
                        inputs_per_object[object_id][idx] = object_mask

            # run inference separately for each object in the video
            object_ids = sorted(inputs_per_object)
            output_scores_per_object = defaultdict(dict)
            for object_id in object_ids:
                # add those input masks to SAM 2 inference state before propagation
                input_frame_inds = sorted(inputs_per_object[object_id])
                predictor.reset_state(inference_state)
                for input_frame_idx in input_frame_inds:
                    predictor.add_new_mask(
                        inference_state=inference_state,
                        frame_idx=input_frame_idx,
                        obj_id=object_id,
                        mask=inputs_per_object[object_id][input_frame_idx],
                    )

                # run propagation throughout the video and collect the results in a dict
                for out_frame_idx, _, out_mask_logits in predictor.propagate_in_video(
                    inference_state,
                    start_frame_idx=min(input_frame_inds),
                    reverse=False,
                ):
                    obj_scores = out_mask_logits.cpu().numpy()
                    output_scores_per_object[object_id][out_frame_idx] = obj_scores
                print(f"completed VOS inference for {object_id}")

            # post-processing: consolidate the per-object scores into per-frame masks
            print("Creating output folder...")
            os.makedirs(os.path.join(output_mask_dir, video_name), exist_ok=True)
            output_palette = input_palette or DAVIS_PALETTE
            video_segments = {}  # video_segments contains the per-frame segmentation results
            print("Starting post-processing...")
            for frame_idx in tqdm(range(len(frame_names)), desc="Post Processing..."):
                scores = torch.full(
                    size=(len(object_ids), 1, height, width),
                    fill_value=-1024.0,
                    dtype=torch.float32,
                )
                for i, object_id in enumerate(object_ids):
                    if frame_idx in output_scores_per_object[object_id]:
                        scores[i] = torch.from_numpy(
                            output_scores_per_object[object_id][frame_idx]
                        )

                if not per_obj_png_file:
                    try:
                        scores = predictor._apply_non_overlapping_constraints(scores)
                        per_obj_output_mask = {
                            object_id: (scores[i] > score_thresh).cpu().numpy()
                            for i, object_id in enumerate(object_ids)
                        }
                    except Exception as e:
                        print(f"Error applying non-overlapping constraints: {e}")
                        per_obj_output_mask = {}
                # video_segments[frame_idx] = per_obj_output_mask
                save_masks_to_dir(
                    output_mask_dir=output_mask_dir,
                    video_name=video_name,
                    frame_name=frame_names[frame_idx],
                    per_obj_output_mask=per_obj_output_mask,
                    height=height,
                    width=width,
                    per_obj_png_file=per_obj_png_file,
                    output_palette=output_palette,
                )
                
                # Explicitly free memory
                del scores
                del per_obj_output_mask
                torch.cuda.empty_cache()
            predictor.reset_state(inference_state)
    except Exception as e:
        print(f"Error processing video {video_name}: {e}")
    finally:
        flatten_folder(os.path.join(base_video_dir, video_name))

    # write the output masks as palette PNG files to output_mask_dir
    # for frame_idx, per_obj_output_mask in video_segments.items():
    #     save_masks_to_dir(
    #         output_mask_dir=output_mask_dir,
    #         video_name=video_name,
    #         frame_name=frame_names[frame_idx],
    #         per_obj_output_mask=per_obj_output_mask,
    #         height=height,
    #         width=width,
    #         per_obj_png_file=per_obj_png_file,
    #         output_palette=output_palette,
    #     )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sam2_cfg",
        type=str,
        default="configs/sam2.1/sam2.1_hiera_b+.yaml",
        help="SAM 2 model configuration file",
    )
    parser.add_argument(
        "--sam2_checkpoint",
        type=str,
        default="./checkpoints/sam2.1_hiera_base_plus.pt",
        help="path to the SAM 2 model checkpoint",
    )
    parser.add_argument(
        "--base_video_dir",
        type=str,
        required=True,
        help="directory containing videos (as JPEG files) to run VOS prediction on",
    )
    parser.add_argument(
        "--input_mask_dir",
        type=str,
        required=True,
        help="directory containing input masks (as PNG files) of each video",
    )
    parser.add_argument(
        "--video_list_file",
        type=str,
        default=None,
        help="text file containing the list of video names to run VOS prediction on",
    )
    parser.add_argument(
        "--output_mask_dir",
        type=str,
        required=True,
        help="directory to save the output masks (as PNG files)",
    )
    parser.add_argument(
        "--score_thresh",
        type=float,
        default=0.0,
        help="threshold for the output mask logits (default: 0.0)",
    )
    parser.add_argument(
        "--use_all_masks",
        action="store_true",
        help="whether to use all available PNG files in input_mask_dir "
        "(default without this flag: just the first PNG file as input to the SAM 2 model; "
        "usually we don't need this flag, since semi-supervised VOS evaluation usually takes input from the first frame only)",
    )
    parser.add_argument(
        "--per_obj_png_file",
        action="store_true",
        help="whether use separate per-object PNG files for input and output masks "
        "(default without this flag: all object masks are packed into a single PNG file on each frame following DAVIS format; "
        "note that the SA-V dataset stores each object mask as an individual PNG file and requires this flag)",
    )
    parser.add_argument(
        "--apply_postprocessing",
        action="store_true",
        help="whether to apply postprocessing (e.g. hole-filling) to the output masks "
        "(we don't apply such post-processing in the SAM 2 model evaluation)",
    )
    parser.add_argument(
        "--track_object_appearing_later_in_video",
        action="store_true",
        help="whether to track objects that appear later in the video (i.e. not on the first frame; "
        "some VOS datasets like LVOS or YouTube-VOS don't have all objects appearing in the first frame)",
    )
    parser.add_argument(
        "--use_vos_optimized_video_predictor",
        action="store_true",
        help="whether to use vos optimized video predictor with all modules compiled",
    )
    parser.add_argument(
        "--is_lidar",
        action="store_true",
        help="whether the input image is a lidar image",
    )
    parser.add_argument(
        "--clear_non_cond_mem_around_input",
        action="store_true",
        help="whether to clear non-conditional memory around the input frame (default: False)",
    )
    parser.add_argument(
        "--add_all_frames_to_correct_as_cond",
        action="store_true",
        help="whether to add all frames to the conditional memory (default: False)",
    )
    args = parser.parse_args()

    # if we use per-object PNG files, they could possibly overlap in inputs and outputs
    hydra_overrides_extra = [
        "++model.non_overlap_masks=" + ("false" if args.per_obj_png_file else "true")
    ]
    predictor = build_sam2_video_predictor(
        config_file=args.sam2_cfg,
        ckpt_path=args.sam2_checkpoint,
        apply_postprocessing=args.apply_postprocessing,
        hydra_overrides_extra=hydra_overrides_extra,
        vos_optimized=args.use_vos_optimized_video_predictor,
    )
    predictor.clear_non_cond_mem_around_input = args.clear_non_cond_mem_around_input
    predictor.clear_non_cond_mem_for_multi_obj = args.clear_non_cond_mem_around_input
    predictor.add_all_frames_to_correct_as_cond = args.add_all_frames_to_correct_as_cond

    if args.use_all_masks:
        print("using all available masks in input_mask_dir as input to the SAM 2 model")
    else:
        print(
            "using only the first frame's mask in input_mask_dir as input to the SAM 2 model"
        )
    # if a video list file is provided, read the video names from the file
    # (otherwise, we use all subdirectories in base_video_dir)
    if args.video_list_file is not None:
        with open(args.video_list_file, "r") as f:
            video_names = [v.strip() for v in f.readlines()]
    else:
        video_names = [
            p
            for p in os.listdir(args.base_video_dir)
            if os.path.isdir(os.path.join(args.base_video_dir, p))
        ]
    print(f"running VOS prediction on {len(video_names)} videos:\n{video_names}")

    for n_video, video_name in enumerate(video_names):
        print(f"\n{n_video + 1}/{len(video_names)} - running on {video_name}")
        if '20250625_Brescia_NIR' in video_name or '20250625_Brescia_REFLEC' in video_name:
            print("Skipping video 20250625_Brescia_NIR")
            continue
        if not args.track_object_appearing_later_in_video:
            vos_inference(
                predictor=predictor,
                base_video_dir=args.base_video_dir,
                input_mask_dir=args.input_mask_dir,
                output_mask_dir=args.output_mask_dir,
                video_name=video_name,
                score_thresh=args.score_thresh,
                use_all_masks=args.use_all_masks,
                per_obj_png_file=args.per_obj_png_file,
            )
        else:
            vos_separate_inference_per_object(
                predictor=predictor,
                base_video_dir=args.base_video_dir,
                input_mask_dir=args.input_mask_dir,
                output_mask_dir=args.output_mask_dir,
                video_name=video_name,
                score_thresh=args.score_thresh,
                use_all_masks=args.use_all_masks,
                per_obj_png_file=args.per_obj_png_file,
                is_lidar=args.is_lidar,
            )

    print(
        f"completed VOS prediction on {len(video_names)} videos -- "
        f"output masks saved to {args.output_mask_dir}"
    )


if __name__ == "__main__":
    main()
