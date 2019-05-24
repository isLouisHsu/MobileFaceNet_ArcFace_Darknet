#ifndef __CROP_ALIGN_H
#define __CROP_ALIGN_H

#include <opencv/cv.h>
#include <opencv/highgui.h>
#include "darknet.h"
#include "mtcnn.h"

image crop_image_by_box(image im, bbox a, int h, int w);
image align_image_with_landmark(image im, landmark src, landmark dst);

#endif