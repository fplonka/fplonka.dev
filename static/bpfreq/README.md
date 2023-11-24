# Overview

bpfreq visualises the frequencies of different pairs of bytes in a file as an image. For example, if the byte `AABB` (= the bits 1010101010111011) appears often in a file, the pixel in the image at the (x='AA', B='BB') coordinate will be bright.

For files with a lot of structure in their binary representation, this can reveal interesting patterns. For compressed files, the resulting image will be mostly noise (since if it wasn't, the regularities could be exploited to compress the file further). Particularly interesting examples are given below.

# Examples
