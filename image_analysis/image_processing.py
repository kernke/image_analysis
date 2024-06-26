# -*- coding: utf-8 -*-
"""
@author: kernke

image in image out

"""
import cv2
import numpy as np
from skimage import  exposure
import copy
from numba import njit

# internal use functions
#%% _aysmmetric_non_maximum_suppression
@njit
def _aysmmetric_non_maximum_suppression(
    newimg, img, cimg, rimg, mask, thresh_ratio, ksize, asympix, damping
):
    ioffs = ksize // 2
    joffs = ksize // 2 + asympix // 2

    for i in range(ioffs, img.shape[0] - ioffs):
        for j in range(joffs, img.shape[1] - joffs):
            if not mask[i, j]:
                pass
            elif (
                not mask[i - ioffs, j - joffs]
                or not mask[i + ioffs, j + joffs]
                or not mask[i - ioffs, j + joffs]
                or not mask[i + ioffs, j - joffs]
            ):
                pass
            else:
                v = max(cimg[i, j - joffs : j + joffs + 1])
                h = max(rimg[i - ioffs : i + ioffs + 1, j]) * ksize / (ksize + asympix)

                if h > v * thresh_ratio:
                    newimg[i, j] = img[i, j]
                else:
                    newimg[i, j] = (
                        img[i, j] / damping
                    )  # np.min(img[i-ioffs:i+ioffs+1,j-joffs:j+joffs+1])
    return newimg



#external use

#%% morphLaplace
def img_morphLaplace(image, kernel):
    return cv2.erode(image, kernel) + cv2.dilate(image, kernel) - 2 * image - 128


#%% gammaCorrection
def img_gammaCorrection(src, gamma):
    invGamma = 1 / gamma

    table = [((i / 255) ** invGamma) * 255 for i in range(256)]
    table = np.array(table, np.uint8)

    return cv2.LUT(src, table)
#%%
def img_to_uint8(img):
    img -= np.min(img)
    return (img / np.max(img) * 255.5).astype(np.uint8)


def img_to_uint16(img):
    img -= np.min(img)
    return (img / np.max(img) * 65535.5).astype(np.uint16)



#%% noise_line_suppression


def img_noise_line_suppression(image, ksize_erodil):
    erod_img = cv2.erode(image, np.ones([1, ksize_erodil]))
    return cv2.dilate(erod_img, np.ones([1, ksize_erodil]))

#%% rebin
def img_rebin(arr, new_shape):
    """reduce the resolution of an image MxN to mxn by taking an average,
    whereby M and N must be multiples of m and n"""
    shape = (
        new_shape[0],
        arr.shape[0] // new_shape[0],
        new_shape[1],
        arr.shape[1] // new_shape[1],
    )
    return arr.reshape(shape).mean(-1).mean(1)

#%% make_square


def img_make_square(image, startindex=None):
    """
    crops the largest square image from the original, by default from the center.
    The position of the cropped square can be specified via startindex,
    moving the frame from the upper left corner at startindex=0
    to the lower right corner at startindex=|M-N|

    Parameters
    ----------
    image: MxN array 
    startindex:  int, 0 <= startindex <= |M-N| 

    Returns:
    square_image either MxM or NxN array
    """

    ishape = image.shape
    index_small, index_big = np.argsort(ishape)

    roi = np.zeros([2, 2], dtype=int)

    roi[index_small] = [0, ishape[index_small]]

    delta = np.abs(ishape[1] - ishape[0])

    if startindex is None:
        startindex = np.floor(delta / 2)
    else:
        if startindex > delta or startindex < 0:
            print("Error: Invalid startindex")
            print("0 <= startindex <= " + str(delta))

    roi[index_big] = startindex, startindex + ishape[index_small]

    square_image = image[roi[0, 0] : roi[0, 1], roi[1, 0] : roi[1, 1]]

    return square_image


#%% rotate

# this function is a modified version of the original from
# https://github.com/PyImageSearch/imutils/blob/master/imutils/convenience.py#L41
def img_rotate_bound(image, angle, flag="cubic", bm=1):
    """
    rotates an image by the given angle clockwise;
    The rotated image is given in a rectangular bounding box
    without cutting off parts of the original image.

    Parameters
    ----------
    image : MxN array, np.uint8
    angle : float, angle given in degrees
    flag : string, optional, possibilities:"cubic","linear";
        sets the method of interplation. The default is "cubic".
    bm : int, optional, possibilities: 0,1;
        sets the border mode, extrapolating from the borders of the image.
        0: continues the image by padding zeros
        1: continues the image by repeating the border-pixel values
        The default is 1.
        (As bm=1 allows more exact back transformation, avoiding the 
         decrease of border-pixel values due to interpolation with zeros.)

    Returns
    -------
    rotated_image: KxL array, np.uint8
    log : list, [M,N,inverse_rotation_matrix],
        contains the original shape M,N and the matrix needed 
        to invert the rotation for the function img_rotate_back
    """

    (h, w) = image.shape[:2]
    (cX, cY) = (w / 2, h / 2)

    # grab the rotation matrix (applying the negative of the
    # angle to rotate clockwise), then grab the sine and cosine
    # (i.e., the rotation components of the matrix)
    M = cv2.getRotationMatrix2D((cX, cY), -angle, 1.0)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])

    # compute the new bounding dimensions of the image
    nW = int(np.round((h * sin) + (w * cos)))
    nH = int(np.round((h * cos) + (w * sin)))

    if bm == 0:
        bm = cv2.BORDER_CONSTANT
    elif bm == 1:
        bm = cv2.BORDER_REPLICATE

    # adjust the rotation matrix to take into account translation
    M[0, 2] += (nW / 2) - cX
    M[1, 2] += (nH / 2) - cY

    invRotateMatrix = cv2.invertAffineTransform(M)
    log = [(h, w), invRotateMatrix]
    # perform the actual rotation and return the image
    if flag == "cubic":
        return (
            cv2.warpAffine(image, M, (nW, nH), flags=cv2.INTER_CUBIC, borderMode=bm),
            log,
        )
    else:
        return (
            cv2.warpAffine(image, M, (nW, nH), flags=cv2.INTER_LINEAR, borderMode=bm),
            log,
        )


#%% rotate back
def img_rotate_back(image, log, flag="cubic", bm=1):
    """
    invert the rotation done by img_rotate_bound returning the image
    to its original shape MxN, cutting away padded values for the
    bounding box generated by img_rotate_bound

    Parameters
    ----------
    image : KxL array, np.uint8
    log : list, [M,N,inverse_rotation_matrix],
        contains the original shape M,N and the matrix needed 
        to invert the rotation. log is given by the img_rotate_bound.
    flag : string, optional, possibilities:"cubic","linear";
        sets the method of interplation. The default is "cubic".
    bm : int, optional, possibilities: 0,1;
        sets the border mode, extrapolating from the borders of the image.
        0: continues the image by padding zeros
        1: continues the image by repeating the border-pixel values
        The default is 1.
        (As bm=1 allows more exact back transformation, avoiding the 
         decrease of border-pixel values due to interpolation with zeros.)

    Returns
    -------
    inverse_rotated_image, MxN array, np.uint8

    """

    (h, w), invM = log

    if bm == 0:
        bm = cv2.BORDER_CONSTANT
    elif bm == 1:
        bm = cv2.BORDER_REPLICATE

    if flag == "cubic":
        return cv2.warpAffine(image, invM, (w, h), flags=cv2.INTER_CUBIC, borderMode=bm)
    else:
        return cv2.warpAffine(
            image, invM, (w, h), flags=cv2.INTER_LINEAR, borderMode=bm
        )



#%% tiling


def img_periodic_tiling(img, tiles=3):
    """
    takes an image as a tile and creates a tiling of
    tiles x tiles by duplicating it. 
    
    Parameters
    ----------
    img : MxN array, image
    tiles : int (must be uneven), optional
        number of tiles in vertical and horizontal direction. 
        The default is 3.

    Returns
    -------
    tiled : tiles*M x tiles*N array
    orig : tuples containing the bounding coordinates of the center image
           ((lower_row_limit,upper_row_limit),(lower_column_limit,upper_column_limit)
    """
    s = np.array(img.shape)
    tiled = np.zeros(s * tiles, dtype=img.dtype)
    for i in range(tiles):
        for j in range(tiles):
            tiled[s[0] * i : s[0] * (i + 1), s[1] * j : s[1] * (j + 1)] = img

    oij = tiles // 2
    orig = (s[0] * oij, s[0] * (oij + 1)), (s[1] * oij, s[1] * (oij + 1))
    return tiled, orig


#%%

def img_transform(image, imshape, rfftmask, rebin=True):
    """
    special function that resizes an image to imshape,
    afterwards applies a Fourier-space mask given by rfftmask,
    and finally rebins squares of 4 pixels to 1 pixel, if rebin=True

    Parameters
    ----------
    image : MxN array
    imshape : [int,int], if rebin=True both integers of imshape must be even 
    rfftmask : [Mx(N/2+1)] array, mask in Fourier space
    rebin : bool, optional
        The default is True.

    Returns
    -------
    transformed_image: KxL array
    """
    # imshape must be even for rebin
    image[image <= 0] = 1
    image = np.log(image)
    resized = cv2.resize(image, imshape[::-1])
    fftimage = np.fft.rfft2(resized)
    inv = np.fft.irfft2(rfftmask * fftimage).real
    equ = exposure.equalize_adapthist(
        inv / np.max(inv), kernel_size=[128, 128], nbins=256
    )
    if rebin:
        rebin_shape = np.array(imshape) // 2
        equ = img_rebin(equ, rebin_shape)
    equ -= np.min(equ)
        
    return (equ / np.max(equ) * 254 + 1).astype(np.uint8)


#%%
def img_transform_minimal(image, imshape,kernel):
    """
    special function that resizes an image to imshape,

    Parameters
    ----------
    image : MxN array
    imshape : [int,int], if rebin=True both integers of imshape must be even 

    Returns
    -------
    transformed_image: KxL array
    """
    image[image <= 0] = 1
    image = np.log(image)
    equ = cv2.resize(image, imshape[::-1])
    equ=(equ / np.max(equ) * 254 + 1).astype(np.uint8)
    lapl = img_morphLaplace(equ, kernel)
    summed = np.zeros(lapl.shape, dtype=np.double)
    summed += 255 - lapl
    summed += equ
    copt = img_to_uint8(summed)
    
    new = exposure.equalize_adapthist(
        copt / np.max(copt), kernel_size=[32, 32], nbins=256
    )
    return img_to_uint8(new)#(equ / np.max(equ) * 254 + 1).astype(np.uint8)
#%% asymmetric non maximum supppression


def img_anms(img, mask, thresh_ratio=1.5, ksize=5, asympix=0, damping=5):
    
    newimg = copy.deepcopy(img)
    cimg = cv2.sepFilter2D(
        img, cv2.CV_64F, np.ones(1), np.ones(ksize), borderType=cv2.BORDER_ISOLATED
    )
    rimg = cv2.sepFilter2D(
        img,
        cv2.CV_64F,
        np.ones(ksize + asympix),
        np.ones(1),
        borderType=cv2.BORDER_ISOLATED,
    )
    return _aysmmetric_non_maximum_suppression(
        newimg, img, cimg, rimg, mask, thresh_ratio, ksize, asympix, damping
    )


