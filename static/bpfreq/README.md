# Overview

bpfreq visualises the frequencies of different pairs of bytes in a file as an image. For example, if the byte pair `AABB` (= the bits 1010101010111011) appears often in a file, the pixel in the image at the (x='AA', y='BB') coordinate will be bright.

For files with a lot of structure in their binary representation, this can reveal interesting patterns. For compressed files, the resulting image will be mostly noise (since if it wasn't, the regularities could be exploited to compress the file further). Particularly interesting examples are given below.

# Examples

.psd

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/2993c2af-927e-4d6a-a97e-f2da84fa5be1)

.xcf

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/a1bf1cc4-1ca1-44ec-aede-f9c5192fd619)

.wav

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/0f9d76d6-1f39-4375-84d6-49e1f44ea61f)

.wav

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/66d62823-3454-4187-b502-3b7539920392)

.ttf

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/9818226a-1bf2-4989-9952-ea3028bdd729)

.ttf

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/2c0b4a36-69d2-4b07-b911-1b5ce32ab722)

.png

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/d9a90a1f-6716-4b4f-a95f-7ca519b0fc5d)

.mp3

![image](https://github.com/fplonka/fplonka.dev/assets/92261790/bf07d6a0-fb45-4bf5-a0da-8ac2d6a96e73)
