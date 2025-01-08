import torch
import numpy as np
import cv2

def resize_with_aspect_ratio(img, target_size, target_dim='width', interpolation=cv2.INTER_CUBIC):
    """等比例缩放图片"""
    h, w = img.shape[:2]
    if target_dim == 'width':
        aspect = h / w
        new_w = target_size
        new_h = int(aspect * new_w)
    else:
        aspect = w / h
        new_h = target_size
        new_w = int(aspect * new_h)
    return cv2.resize(img, (new_w, new_h), interpolation=interpolation)

def create_canvas_with_image(canvas_size, image, position, bg_color, is_mask=False):
    """在画布上放置图片
    Args:
        canvas_size: (width, height)
        image: 输入图像
        position: 位置 (top/center/bottom)
        bg_color: 背景颜色
        is_mask: 是否是遮罩图像
    """
    # 确保画布尺寸正确（宽度在前，高度在后）
    canvas_w, canvas_h = canvas_size
    
    # 获取图像尺寸，处理单通道或三通道情况
    if len(image.shape) == 2:
        img_h, img_w = image.shape
    else:
        img_h, img_w = image.shape[:2]
    
    # 创建画布
    if is_mask:
        canvas = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    else:
        canvas = np.full((canvas_h, canvas_w, 3), bg_color, dtype=np.uint8)
    
    # 计算水平居中位置
    x = (canvas_w - img_w) // 2
    
    # 根据位置计算垂直位置
    if position == "top":
        y = 0
    elif position == "bottom":
        y = canvas_h - img_h
    else:  # center
        y = (canvas_h - img_h) // 2
    
    # 确保坐标不会为负
    x = max(0, min(x, canvas_w - img_w))
    y = max(0, min(y, canvas_h - img_h))
    
    # 放置图片
    try:
        # 确保图片数据类型正确
        if not is_mask:
            image = image.astype(np.uint8)
        canvas[y:y+img_h, x:x+img_w] = image
    except ValueError as e:
        print(f"Debug info: canvas_shape={canvas.shape}, image_shape={image.shape}, x={x}, y={y}, img_w={img_w}, img_h={img_h}, is_mask={is_mask}")
        raise e
    
    return canvas

class ImageCombineforIC:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "first_image": ("IMAGE",),
                "second_image": ("IMAGE",),
                "reference_edge": (["image1_width", "image1_height", "image2_width", "image2_height"], {
                    "default": "image1_width",
                }),
                "combine_mode": (["horizontal", "vertical"], {
                    "default": "horizontal",
                }),
                "second_image_scale": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1
                }),
                "second_image_position": (["top", "center", "bottom", "left", "right"], {
                    "default": "center",
                }),
                "final_size": ("INT", {
                    "default": 1024,
                    "min": 64,
                    "max": 8192,
                    "step": 64
                }),
                "background_color": ("STRING", {
                    "default": "#FFFFFF",
                    "multiline": False,
                }),
            },
            "optional": {
                "first_mask": ("MASK",),
                "second_mask": ("MASK",),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "MASK", "MASK", "TUPLE", "TUPLE")
    RETURN_NAMES = ("IMAGE", "MASK", "FIRST_MASK", "SECOND_MASK", "first_size", "second_size")
    FUNCTION = "combine_images"
    CATEGORY = "YiCheng/Image"

    def combine_images(self, first_image, second_image, reference_edge, combine_mode, 
                      second_image_scale, second_image_position, final_size, background_color,
                      first_mask=None, second_mask=None):
        # 获取输入图像并确保数据类型正确
        image1 = (first_image[0].detach().cpu().numpy() * 255).astype(np.uint8)
        image2 = (second_image[0].detach().cpu().numpy() * 255).astype(np.uint8)
        
        # 获取原始尺寸
        h1, w1 = image1.shape[:2]
        h2, w2 = image2.shape[:2]

        # 确定基准图和第二张图
        if reference_edge.startswith('image1'):
            base_image = image1
            base_mask = first_mask[0].numpy() if first_mask is not None else np.zeros((h1, w1))
            second_img = image2
            second_img_mask = second_mask[0].numpy() if second_mask is not None else np.zeros((h2, w2))
            target_size = w1 if reference_edge.endswith('width') else h1
        else:
            base_image = image2
            base_mask = second_mask[0].numpy() if second_mask is not None else np.zeros((h2, w2))
            second_img = image1
            second_img_mask = first_mask[0].numpy() if first_mask is not None else np.zeros((h1, w1))
            target_size = w2 if reference_edge.endswith('width') else h2

        # 转换背景颜色
        if background_color.startswith('#'):
            bg_color = tuple(int(background_color[i:i+2], 16) for i in (5, 3, 1))[::-1]

        # 等比例缩放图片
        target_dim = 'width' if reference_edge.endswith('width') else 'height'
        scaled_second = resize_with_aspect_ratio(second_img, target_size, target_dim)
        scaled_second_mask = resize_with_aspect_ratio(second_img_mask, target_size, target_dim, cv2.INTER_NEAREST)
        
        # 第二张图片额外缩放
        if second_image_scale != 1.0:
            h, w = scaled_second.shape[:2]
            new_w = int(w * second_image_scale)
            new_h = int(h * second_image_scale)
            scaled_second = cv2.resize(scaled_second, (new_w, new_h))
            scaled_second_mask = cv2.resize(scaled_second_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

        # 获取最终尺寸
        base_h, base_w = base_image.shape[:2]
        second_h, second_w = scaled_second.shape[:2]
        
        # 创建最终画布
        if combine_mode == "horizontal":
            canvas_w = base_w + second_w
            canvas_h = max(base_h, second_h)
        else:
            canvas_w = max(base_w, second_w)
            canvas_h = base_h + second_h

        # 创建画布
        final_canvas = np.full((canvas_h, canvas_w, 3), bg_color, dtype=np.uint8)
        final_mask = np.zeros((canvas_h, canvas_w), dtype=np.uint8)

        # 放置基准图（总是在左边或顶部）
        y1 = (canvas_h - base_h) // 2 if combine_mode == "horizontal" else 0
        x1 = 0
        final_canvas[y1:y1+base_h, x1:x1+base_w] = base_image
        final_mask[y1:y1+base_h, x1:x1+base_w] = base_mask

        # 创建第二张图片的画布
        if combine_mode == "horizontal":
            second_canvas_size = (second_w, canvas_h)
            x_offset = base_w
            y_offset = 0
        else:
            second_canvas_size = (canvas_w, second_h)
            x_offset = 0
            y_offset = base_h

        # 处理左右位置选项
        if second_image_position in ["left", "right"]:
            # 如果是左右位置，需要调整水平偏移
            if second_image_position == "left":
                x = 0
            else:  # right
                x = second_canvas_size[0] - scaled_second.shape[1]
            # 垂直居中
            y = (second_canvas_size[1] - scaled_second.shape[0]) // 2
        else:
            # 原有的上中下位置逻辑
            x = (second_canvas_size[0] - scaled_second.shape[1]) // 2
            if second_image_position == "top":
                y = 0
            elif second_image_position == "bottom":
                y = second_canvas_size[1] - scaled_second.shape[0]
            else:  # center
                y = (second_canvas_size[1] - scaled_second.shape[0]) // 2

        # 创建第二张图片的画布
        second_canvas = np.full((second_canvas_size[1], second_canvas_size[0], 3), bg_color, dtype=np.uint8)
        second_mask_canvas = np.zeros((second_canvas_size[1], second_canvas_size[0]), dtype=np.uint8)
        
        # 放置第二张图片
        second_canvas[y:y+scaled_second.shape[0], x:x+scaled_second.shape[1]] = scaled_second
        second_mask_canvas[y:y+scaled_second.shape[0], x:x+scaled_second.shape[1]] = scaled_second_mask

        # 将第二张图片放入最终画布
        if combine_mode == "horizontal":
            final_canvas[:, x_offset:] = second_canvas
            final_mask[:, x_offset:] = second_mask_canvas
        else:
            final_canvas[y_offset:, :] = second_canvas
            final_mask[y_offset:, :] = second_mask_canvas

        # 最终尺寸调整
        if combine_mode == "horizontal":
            aspect = canvas_h / canvas_w
            new_w = final_size
            new_h = int(aspect * new_w)
        else:
            aspect = canvas_w / canvas_h
            new_h = final_size
            new_w = int(aspect * new_h)

        # 调整最终画布尺寸
        final_canvas = cv2.resize(final_canvas, (new_w, new_h))
        final_mask = cv2.resize(final_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

        # 创建分离的遮罩
        # 为第一张图片创建遮罩画布
        first_separate_mask = np.zeros((new_h, new_w), dtype=np.uint8)
        # 为第二张图片创建遮罩画布
        second_separate_mask = np.zeros((new_h, new_w), dtype=np.uint8)

        # 计算缩放比例
        scale_w = new_w / canvas_w
        scale_h = new_h / canvas_h

        # 计算第一张图片在最终画布中的位置和尺寸
        x1_scaled = int(x1 * scale_w)
        y1_scaled = int(y1 * scale_h)
        w1_scaled = int(base_w * scale_w)
        h1_scaled = int(base_h * scale_h)

        # 计算第二张图片在最终画布中的位置和尺寸
        x2_scaled = int(x_offset * scale_w)
        y2_scaled = int(y_offset * scale_h)
        w2_scaled = int(second_canvas_size[0] * scale_w)
        h2_scaled = int(second_canvas_size[1] * scale_h)

        # 填充分离的遮罩
        first_separate_mask[y1_scaled:y1_scaled+h1_scaled, x1_scaled:x1_scaled+w1_scaled] = 255
        second_separate_mask[y2_scaled:y2_scaled+h2_scaled, x2_scaled:x2_scaled+w2_scaled] = 255

        # 转换为 torch tensor
        final_canvas = final_canvas.astype(np.float32) / 255.0
        final_canvas = torch.from_numpy(final_canvas)[None,]
        final_mask = torch.from_numpy(final_mask)[None,]
        first_separate_mask = torch.from_numpy(first_separate_mask)[None,]
        second_separate_mask = torch.from_numpy(second_separate_mask)[None,]

        # 返回整合后的尺寸信息
        first_size = (w1, h1)
        second_size = (w2, h2)

        return (final_canvas, final_mask, first_separate_mask, second_separate_mask, first_size, second_size)

NODE_CLASS_MAPPINGS = {
    "ImageCombineforIC": ImageCombineforIC
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageCombineforIC": "Image Combine For IC"
} 