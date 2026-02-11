from PIL import Image
import numpy as np

# 간단한 그라데이션 이미지 생성
width, height = 800, 600
image_array = np.zeros((height, width, 3), dtype=np.uint8)

# 파란색에서 보라색으로 그라데이션
for y in range(height):
    for x in range(width):
        image_array[y, x] = [
            int(x / width * 255),      # Red
            int(y / height * 128),      # Green  
            200                         # Blue
        ]

# PIL Image로 변환
image = Image.fromarray(image_array, 'RGB')

# TIF 파일로 저장
output_path = './sample.tif'
image.save(output_path, format='TIFF')

print(f"TIF 파일이 생성되었습니다: {output_path}")