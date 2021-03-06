## This implementation is modified based on the pytorch version of 3DDFA: 
## # https://github.com/cleardusk/3DDFA
## wirtten in python 3.5

import numpy as np
import math

from scipy.spatial import Delaunay
from copy import deepcopy
from collections import defaultdict

from . import pyFaceFrontalization as pyFF
from .pyMM3D import pyMM3D as pyMM


def ProjectShape(vertex, fR, T, roi_bbox, STD_SIZE=120):    
    # transform to image coordinate scale
    vertex = fR.dot(vertex) + T
    vertex[1,:] = STD_SIZE + 1 - vertex[1,:]
    
    sx, sy, ex, ey = roi_bbox
    scale_x = (ex - sx) / STD_SIZE
    scale_y = (ey - sy) / STD_SIZE
    vertex[0, :] = vertex[0, :] * scale_x + sx
    vertex[1, :] = vertex[1, :] * scale_y + sy

    s = (scale_x + scale_y) / 2
    vertex[2, :] *= s
    
    return vertex


def ParaMap_Pose(para_Pose):
    para_Pose = np.squeeze(para_Pose)
    phi, gamma, theta = para_Pose[:3]
    t3d = para_Pose[3:6]
    f = para_Pose[-1]
    
    return phi, gamma, theta, t3d, f


def ZBuffer(projectedVertex, tri, texture, img_src):
    projectedVertex = projectedVertex - 1
    # tri = tri - 1
    height, width, nChannels = img_src.shape
    nver = projectedVertex.shape[1]
    ntri = tri.shape[1]
    
    # make sure they are F-contiguous
    if not projectedVertex.flags.f_contiguous:
        projectedVertex = projectedVertex.copy(order='F')
    if not tri.flags.f_contiguous:
        tri = tri.copy(order='F')
    if tri.dtype != np.float64:
        tri = tri.astype(np.float64)
    if not texture.flags.f_contiguous:
        texture = texture.copy(order='F')
    if not img_src.flags.f_contiguous:
        img_src = img_src.copy(order='F')
    
    img, tri_ind = pyMM().ZBuffer(projectedVertex, tri, texture, img_src, nver, ntri, width, height, nChannels)     
    # tri_ind = tri_ind + 1
    
    return np.squeeze(img), np.squeeze(tri_ind)


def ZBufferTri(projectedVertex, tri, texture_tri, img_src):
    projectedVertex = projectedVertex - 1
    # tri = tri - 1
    height, width, nChannels = img_src.shape
    nver = projectedVertex.shape[1]
    ntri = tri.shape[1]
    
    # make sure they are F-contiguous
    if not projectedVertex.flags.f_contiguous:
        projectedVertex = projectedVertex.copy(order='F')
    if not tri.flags.f_contiguous:
        tri = tri.copy(order='F')
    if tri.dtype != np.float64:
        tri = tri.astype(np.float64)
    if not texture_tri.flags.f_contiguous:
        texture_tri = texture_tri.copy(order='F')
    if not img_src.flags.f_contiguous:
        img_src = img_src.copy(order='F')
    
    img, tri_ind = pyMM().ZBufferTri(projectedVertex, tri, texture_tri, img_src, nver, ntri, width, height, nChannels)    
    # tri_ind = tri_ind + 1
    
    return np.squeeze(img), np.squeeze(tri_ind)


def RotationMatrix(pitch, yaw, roll, zyx_order=True):
    # get rotation matrix by rotate angle    
    R_x = np.array([[1.0, 0.0, 0.0], [0.0, np.cos(pitch), -np.sin(pitch)], [0.0, np.sin(pitch), np.cos(pitch)]])
    R_y = np.array([[np.cos(yaw), 0.0, np.sin(yaw)], [0.0, 1.0, 0.0], [-np.sin(yaw), 0.0, np.cos(yaw)]])
    R_z = np.array([[np.cos(roll), -np.sin(roll), 0.0,], [np.sin(roll), np.cos(roll), 0.0], [0.0, 0.0, 1.0]])    
    if zyx_order:
        return R_z @ R_y @ R_x
    else:
        return R_x @ R_y @ R_z


def KeypointsWithPose(pitch, yaw, roll, vertex, tri, isoline, keypoints, modify_ind, candidates=None):    
    ProjectVertex = np.dot(RotationMatrix(pitch, yaw, 0), vertex)
    ProjectVertex = ProjectVertex - np.min(ProjectVertex, axis=1)[:, np.newaxis] + 1
    ProjectVertex /= np.max(np.abs(ProjectVertex))
    
    keypoints_pose = deepcopy(keypoints)
    # 1. get the keypoints needing modifying
    modify_key = deepcopy(modify_ind)
    # 2. get the contour line of each modify key
    contour_line = [isoline[i] for i in modify_key]

    if candidates is not None:
        candidates = candidates[modify_key]
        for i in range(len(modify_key)):
            if len(candidates[i]) > 0:
                contour_line[i] = sorted(list(set(contour_line[i]).intersection(set(candidates[i]))))
    # 3. get the outest point on the contour line
    for i in range(len(modify_key)):
        if yaw <= 0:
            min_ind = np.argmin(ProjectVertex[0, contour_line[i]])
            keypoints_pose[modify_key[i]] = contour_line[i][min_ind]
        else:
            max_ind = np.argmax(ProjectVertex[0, contour_line[i]])          
            keypoints_pose[modify_key[i]] = contour_line[i][max_ind]

    return keypoints_pose            


def imgContourBbox(bbox, wpnum):    
    wp_num = wpnum - 2
    
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]    

    hp_num = round(height / width * (wp_num+2)) - 2
    w_inter = (width-1) / (wp_num+1)
    h_inter = (height-1) / (hp_num+1)
    # up edge
    start_point = bbox[[0,1], np.newaxis]
    interval = np.array([w_inter,0])[:, np.newaxis]
    img_contour = start_point + np.arange(0,1+wp_num)*interval
    # right edge
    start_point = bbox[[2,1], np.newaxis]
    interval = np.array([0,h_inter])[:, np.newaxis]
    img_contour = np.hstack([img_contour, start_point + np.arange(0,1+hp_num)*interval])
    # down edge
    start_point = bbox[[2,3], np.newaxis]
    interval = np.array([-w_inter,0])[:, np.newaxis]
    img_contour = np.hstack([img_contour, start_point + np.arange(0,1+wp_num)*interval])
    # left edge
    start_point = bbox[[0,3], np.newaxis]
    interval = np.array([0,-h_inter])[:, np.newaxis]
    img_contour = np.hstack([img_contour, start_point + np.arange(0,1+hp_num)*interval])

    return img_contour, int(wp_num), int(hp_num)


def EliminateInternalTri(cont_ver, tri):    
    valid_bin = np.zeros(tri.shape[1], dtype=np.bool)

    for i in range(cont_ver.shape[1]):
        # for each contour point, find its related tri
        tmp_bin = np.any(tri == i, axis=0)
        conn_tri_ind = np.where(tmp_bin == True)[0]
        conn_tri = tri[:, tmp_bin]
        angle_list = []

        for j in range(conn_tri.shape[1]):
            # for each connected tri, find the angle centered at i         
            other_point = sorted(list(set(conn_tri[:,j]).difference(set([i]))))

            line1 = cont_ver[:2, [i, other_point[0]]]
            line1 = line1[:,1] - line1[:,0]

            line2 = cont_ver[:2, [i, other_point[1]]]
            line2 = line2[:,1] - line2[:,0]

            angle_cos = line1.dot(line2) / np.sqrt(line1.dot(line1)) / np.sqrt(line2.dot(line2))
            angle = np.arccos(angle_cos)
            angle_list.append(angle)        

        if(sum(angle_list) > (350 / 180 * np.pi)):
            # if the sum of angles around the vertex i is 360, it is a concave point
            for j in range(conn_tri.shape[1]):
                # for each connected tri, find the angle centered at i            
                other_point = sorted(list(set(conn_tri[:,j]).difference(set([i]))))            
                # if edge connecting point i is the contour edge, it is a valid triangle
                bin1 = abs(i-other_point[0]) in [1, cont_ver.shape[1]-1]
                bin2 = abs(i-other_point[1]) in [1, cont_ver.shape[1]-1]
                if np.all([bin1, bin2]):
                    valid_bin[conn_tri_ind[j]] = True

    return valid_bin  


def AnchorAdjustment_Z(contour_all, contour_all_ref, adjust_bin, tri, img):
    # height, width, nChannels = img.shape
    adjust_ind = np.where(adjust_bin)[0]
    # Get only z coordinates 
    # We sovle the equation Y = AX
    # where X is the (x,y) of outpoint_des
    # Y and A represent relations between inpoints_src and outpoint_src
    Y_Equ = []
    A_Equ = []
    
    # for each outpoint
    for pt in adjust_ind:    
        # find the corresponding tri    
        tmp_bin = np.any(tri == pt, axis=0)
        # find connecting point
        temp = tri[:, tmp_bin]    
        connect = np.unique(temp)    
        connect = sorted(list(set(connect).difference(set([pt]))))
        for pt_con in connect:
            if adjust_bin[pt_con]:
                # if connected to a point need adjustment, we module their relationships
                z_offset = contour_all_ref[2, pt] - contour_all_ref[2, pt_con]                        
                dis = contour_all_ref[:2, pt] - contour_all_ref[:2, pt_con]
                dis = np.sqrt(dis.dot(dis))
                weight = 1.0
                #weight = 1 / dis; weight = 1;                        
                pt1 = np.where(adjust_ind == pt)[0]
                pt_con1 = np.where(adjust_ind == pt_con)[0]            

                A = np.zeros(len(adjust_ind))
                A[pt1] = 1
                A[pt_con1] = -1                

                A_Equ.append(A * weight)
                Y_Equ.append(z_offset * weight)
            else:
                # if connected to solid point, we module the positions
                z_new = contour_all_ref[2, pt] - contour_all_ref[2, pt_con] + contour_all[2, pt_con]
                dis = contour_all_ref[:2, pt] - contour_all_ref[:2, pt_con]
                dis = np.sqrt(dis.dot(dis))
                weight = 1.0
                #weight = 1 / dis; weight = 1;            
                pt1 = np.where(adjust_ind == pt)[0]
                A = np.zeros(len(adjust_ind))
                A[pt1] = 1                

                A_Equ.append(A * weight)
                Y_Equ.append(z_new * weight)

    A_Equ = np.array(A_Equ)
    Y_Equ = np.array(Y_Equ)

    # get the new position
    X = np.squeeze(np.linalg.lstsq(A_Equ, Y_Equ, rcond=None)[0])
    contour_all_z = deepcopy(contour_all)
    contour_all_z[2,adjust_ind] = X

    return contour_all_z     


def AnchorAdjustment_Rotate(all_vertex_src, all_vertex_ref, all_vertex_adjust, tri, anchor_flags, img):
    # height, width, nChannels = img.shape
    adjust_ind = np.where(np.any([anchor_flags==2, anchor_flags==3], axis=0))[0]        
    # we sovle the equation Y = AX
    # where X is the (x,y) of outpoint_des
    # Y and A represent relations between inpoints_src and outpoint_src
    Y_Equ = []
    A_Equ = []

    # for each outpoint
    for pt in adjust_ind:    
        # find the corresponding tri    
        tmp_bin = np.any(tri == pt, axis=0)
        # find connecting point
        temp = tri[:, tmp_bin]    
        connect = np.unique(temp)    
        connect = sorted(list(set(connect).difference(set([pt]))))
        # the relationship of [pt, pt_con]    
        for pt_con in connect:        
            if anchor_flags[pt] == 2:
                # if base point is a src point, prefer src relation
                if anchor_flags[pt_con] == 1:
                    # if connect to a base point, module the positions
                    x_new = all_vertex_src[0,pt] - all_vertex_src[0,pt_con] + all_vertex_adjust[0,pt_con]
                    y_new = all_vertex_src[1,pt] - all_vertex_src[1,pt_con] + all_vertex_adjust[1,pt_con]

                    pt1 = np.where(adjust_ind == pt)[0]

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1] = 1                                
                    A_Equ.append(A)
                    Y_Equ.append(x_new)

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1+1] = 1                                
                    A_Equ.append(A)
                    Y_Equ.append(y_new)
                else: #(anchor_flags(pt_con) == 2 || adjust_ind(pt_con) == 3)
                    # src-src and src-ref relationships :
                    # based on src relationship
                    x_offset = all_vertex_src[0,pt] - all_vertex_src[0,pt_con]
                    y_offset = all_vertex_src[1,pt] - all_vertex_src[1,pt_con]

                    pt1 = np.where(adjust_ind == pt)[0]
                    pt_con1 = np.where(adjust_ind == pt_con)[0]

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1] = 1
                    A[2*pt_con1] = -1
                    A_Equ.append(A)
                    Y_Equ.append(x_offset)

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1+1] = 1
                    A[2*pt_con1+1] = -1                
                    A_Equ.append(A)
                    Y_Equ.append(y_offset)
            else: # (anchor_flags(pt) == 3)  
                # if it is a ref point, prefer ref relation
                if anchor_flags[pt_con] == 1:
                    # if connect to a base point, module the positions                
                    x_new = all_vertex_ref[0,pt] - all_vertex_ref[0,pt_con] + all_vertex_adjust[0,pt_con]
                    y_new = all_vertex_ref[1,pt] - all_vertex_ref[1,pt_con] + all_vertex_adjust[1,pt_con]                

                    pt1 = np.where(adjust_ind == pt)[0]

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1] = 1                                
                    A_Equ.append(A)
                    Y_Equ.append(x_new)

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1+1] = 1
                    A_Equ.append(A)
                    Y_Equ.append(y_new)
                else: #if(adjust_ind(j) == 3)
                    # ref-ref relationships :
                    # based on ref relationship                
                    x_offset = all_vertex_ref[0,pt] - all_vertex_ref[0,pt_con]
                    y_offset = all_vertex_ref[1,pt] - all_vertex_ref[1,pt_con]

                    pt1 = np.where(adjust_ind == pt)[0]
                    pt_con1 = np.where(adjust_ind == pt_con)[0]

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1] = 1
                    A[2*pt_con1] = -1
                    A_Equ.append(A)
                    Y_Equ.append(x_offset)

                    A = np.zeros(2*len(adjust_ind))
                    A[2*pt1+1] = 1
                    A[2*pt_con1+1] = -1                
                    A_Equ.append(A)
                    Y_Equ.append(y_offset)

    A_Equ = np.array(A_Equ)
    Y_Equ = np.array(Y_Equ)

    # get the new position
    X = np.squeeze(np.linalg.lstsq(A_Equ, Y_Equ, rcond=None)[0])    

    all_vertex_adjust[:2,adjust_ind] = X.reshape((2,-1), order='F')
    all_vertex_adjust[2, adjust_ind] = all_vertex_ref[2, adjust_ind]

    return all_vertex_adjust


def ProjectShape(vertex, fR, T, roi_bbox):
    # function in pytorch 3DDFA
    STD_SIZE = 120
    
    # transform to image coordinate scale
    vertex = fR.dot(vertex) + T
    vertex[1,:] = STD_SIZE + 1 - vertex[1,:]
    
    sx, sy, ex, ey = roi_bbox
    scale_x = (ex - sx) / STD_SIZE
    scale_y = (ey - sy) / STD_SIZE
    vertex[0, :] = vertex[0, :] * scale_x + sx
    vertex[1, :] = vertex[1, :] * scale_y + sy

    s = (scale_x + scale_y) / 2
    vertex[2, :] *= s
    
    return vertex    


def BackProjectShape(vertex, fR, T, roi_bbox): 
    STD_SIZE = 120

    sx, sy, ex, ey = roi_bbox
    scale_x = (ex - sx) / STD_SIZE
    scale_y = (ey - sy) / STD_SIZE
    s = (scale_x + scale_y) / 2

    vertex[2, :] /= s
    vertex[0, :] = (vertex[0, :] - sx)/scale_x
    vertex[1, :] = (vertex[1, :] - sy)/scale_y  

    vertex[1,:] = STD_SIZE + 1 - vertex[1,:]  

    vertex = np.linalg.inv(fR).dot((vertex - T))
    
    return vertex


def ImageMeshing(vertex, tri_plus, vertex_full, tri_full, vertexm_full, ProjectVertex_full, ProjectVertexm_full,
                 fR, T, roi_bbox, f, pitch, yaw, roll, t3d,
                 keypoints, keypointsfull_contour, parallelfull_contour, img, layer_width, eliminate_inner_tri=False):
    # We will mark a set of points to help triangulation the whole image
    # These points are arranged as multiple layers around face contour
    # The layers are set between face contour and bbox
    height, width = img.shape[:2]
    layer = len(layer_width)    
    
    contlist = [[] for _ in range(layer+2)]
    bboxlist = [[] for _ in range(layer+2)]

    # 1. Get the necessary face_contour
    if yaw < 0:
        face_contour_modify = np.array(list(range(8)) + list(range(24,30)))
    else:
        face_contour_modify = np.array(range(9,23))

    face_contour_ind = KeypointsWithPose(pitch, yaw, roll, vertex_full, tri_full,
                                         parallelfull_contour, keypointsfull_contour, face_contour_modify)
    face_contour = ProjectVertex_full[:, face_contour_ind]

    contlist[0] = face_contour
    tl = np.min(face_contour, axis=1)
    br = np.max(face_contour, axis=1)
    bboxlist[0] = np.hstack([tl, br])

    # 2. Get the MultiLayers between face_contour and img_contour
    # other layers
    nosetip = keypoints[33]
    contour_base = face_contour
    face_center = np.mean(contour_base[:2], axis=1)

    for i in range(1,1+layer):
        curlayer_width = 1 + layer_width[i-1]
        contour = face_center[:,np.newaxis] + curlayer_width * (contour_base[:2] - face_center[:,np.newaxis])     
        
        t3d_cur = (1-curlayer_width)*fR.dot(vertex[:,nosetip][:, np.newaxis]) + T

        contour3d = ProjectShape(vertex_full[:,face_contour_ind], curlayer_width*fR, t3d_cur, roi_bbox)
        
        contour = np.vstack([contour, contour3d[2,:]])

        contlist[i] = contour
        tl = np.min(contour[:2,:], axis=1)
        br = np.max(contour[:2,:], axis=1)
        bboxlist[i] = np.hstack([tl, br])

    # Get the img_contour
    wp_num = 7
    bbox1 = bboxlist[layer]
    bbox2 = bboxlist[layer-1]
    margin = bbox1 - bbox2
    bbox = bbox1 + margin
    bbox[0] = min(bbox[0],1)
    bbox[1] = min(bbox[1],1)
    bbox[2] = max(bbox[2],width)
    bbox[3] = max(bbox[3],height)
    bboxlist[layer+1] = bbox
    wp_num1 = round(wp_num / (bbox1[2]-bbox1[0]) * (bbox[2]-bbox[0]))

    img_contour, wp_num, hp_num = imgContourBbox(bbox, wp_num1)
    contlist[layer+1] = np.vstack([img_contour, np.zeros((1,img_contour.shape[1]))])    

    # Triangulation
    contour_all = np.hstack([item for item in contlist if len(item) > 0])
    tri_all = Delaunay(contour_all.T[:,:2]).simplices.T

    # further judge the internal triangles, since there maybe concave tri
    if eliminate_inner_tri:
        inbin = np.all(tri_all<face_contour.shape[1], axis=0)
        tri_inner = tri_all[:, inbin]
        cont_inner = contlist[0]
        valid_inner_tri = EliminateInternalTri(cont_inner, tri_inner)
        tri_inner = tri_all[:, inbin]
        tri_all = np.hstack([tri_all[:,~inbin], tri_inner[:,valid_inner_tri]])

    ## Now we need to determine the z coordinates of each contour point
    # Following the two considerations
    # 1. There always have face regions in the background
    # 2. We don't care about the alignment result of background pixels

    # the z coordinates of img contour out
    img_contour = contlist[-1]
    img_contour_co = range(contour_all.shape[1]-img_contour.shape[1], contour_all.shape[1])

    for i in range(len(img_contour_co)):    
        # find the related triangle
        tmp_bin = np.any(tri_all == img_contour_co[i], axis=0)
        conn_tri = tri_all[:, tmp_bin]    
        conn_point = np.unique(conn_tri)

        conn_face_contour_ind = sorted(list(set(conn_point).difference(set(img_contour_co))))

        if len(conn_face_contour_ind) == 0:
            img_contour[2,i] = np.inf
            continue    

        # get the z coordinates of each connect face contour
        z_coordinates = contour_all[2, conn_face_contour_ind]
        img_contour[2,i] = np.mean(z_coordinates)    

    contlist[-1] = img_contour
    contour_all = np.hstack(contlist)

    # Complement the point with no face contour correspondence
    img_contour_co = np.arange(contour_all.shape[1]-img_contour.shape[1], contour_all.shape[1])

    tmp_bin = np.isinf(img_contour[2,:])
    invalid_co = np.where(tmp_bin==True)[0]

    while len(invalid_co) > 0:   
        valid_co = np.where(~tmp_bin)[0]
        img_contour_co_cur = img_contour_co[valid_co]

        for i in range(len(img_contour_co)):        
            # find the related triangle
            tmp_bin = np.any(tri_all == img_contour_co[i], axis=0)
            conn_tri = tri_all[:, tmp_bin]    
            conn_point = np.unique(conn_tri)

            conn_face_contour_ind = sorted(list(set(conn_point).intersection(set(img_contour_co_cur))))

            if len(conn_face_contour_ind) == 0:
                continue

            # get the z coordinates of each connect face contour
            z_coordinates = contour_all[2, conn_face_contour_ind] 
            img_contour[2,i] = np.mean(z_coordinates)

        contlist[-1] = img_contour
        contour_all = np.hstack(contlist)

        tmp_bin = np.isinf(img_contour[2,:])
        invalid_co = np.where(tmp_bin==True)[0]

    contlist[-1] = img_contour
    contour_all = np.hstack(contlist)

    # Finally refine the anchor depth with real depth
    depth_ref, tri_ind = ZBuffer(ProjectVertex_full, tri_full, ProjectVertexm_full[2,:][np.newaxis,:],
                                 np.zeros((height, width, 1)))
    # # test draw
    # im1 = Image.fromarray(( 255*(depth_ref-np.min(depth_ref))/(np.max(depth_ref)-np.min(depth_ref)) ).astype('uint8'))
    # im2 = Image.fromarray((255*tri_ind/np.max(tri_ind)).astype('uint8'))    

    contour_all_ref = deepcopy(contour_all)
    # contlist_ref = deepcopy(contlist)
    contlist_new = deepcopy(contlist)

    solid_depth_bin_list = [np.zeros(item.shape[1]) for item in contlist]
    solid_depth_bin_list[0] += 1

    for j in list(range(3,14))+list(range(18,30)):
        count = 0        
        for i in range(1,len(contlist_new)-1):        
            ray = contlist_new[i][:,j]
            x, y = np.around(ray[:2]).astype(np.int)
            if np.any([x < 1, x > width, y < 1, y > height]):
                continue
            if tri_ind[y-1, x-1] == -1:
                continue
            count += 1

        if count < 2:
            continue

        for i in range(1,len(contlist_new)-1):
            ray = contlist_new[i][:,j]
            x, y = np.around(ray[:2]).astype(np.int)
            if np.any([x < 1, x > width, y < 1, y > height]):
                continue      
            if tri_ind[y-1, x-1] == -1:
                continue
            contlist_new[i][2,j] = depth_ref[y-1, x-1]
            solid_depth_bin_list[i][j] = 1

    solid_depth_bin = np.hstack(solid_depth_bin_list).astype(np.bool)
    contour_all_new = np.hstack(contlist_new)

    # finally refine non_solid contour
    contour_all_z = AnchorAdjustment_Z(contour_all_new, contour_all_ref, ~solid_depth_bin, tri_all, img)
    contour_all_new[2,:] = contour_all_z[2,:]

    counter = 0
    for i, item in enumerate(contlist):
        contlist[i] = contour_all_new[:, counter:counter+item.shape[1]]
        counter += item.shape[1]  
    
    return contlist, tri_all, face_contour_ind, wp_num, hp_num


def ImageRotation(contlist_src, bg_tri, vertex, tri, face_contour_ind,
                  isoline_face_contour, Pose_Para_src, Pose_Para_ref, img, 
                  ProjectVertex_ref, fR, T, roi_box):
    _, yaw, _, _, f = ParaMap_Pose(Pose_Para_src)
    pitch_ref, yaw_ref, roll_ref, t3d_ref, _ = ParaMap_Pose(Pose_Para_ref)

    all_vertex = np.hstack(contlist_src)
    all_vertex_src = deepcopy(all_vertex)

    # 1. get the preliminary position on the ref frame    
    all_vertex_ref = BackProjectShape(all_vertex, fR, T, roi_box)
    # Go to the reference position
    R_ref = RotationMatrix(pitch_ref, yaw_ref, roll_ref)
    all_vertex_ref = ProjectShape(all_vertex_ref, f*R_ref, t3d_ref[:,np.newaxis], roi_box)
    
    # 2. Landmark marching 
    if yaw < 0:
        face_contour_modify = np.array(list(range(8)) + list(range(24,30)))
    else:
        face_contour_modify = np.array(range(9,23))

    adjust_ind = list(range(3,14)) + list(range(18,30))
    yaw_delta = yaw_ref - yaw
    yaw_temp = yaw + yaw_delta/2.5    

    face_contour_ind  = KeypointsWithPose(pitch_ref, yaw_temp, roll_ref, vertex, tri, 
                                          isoline_face_contour, face_contour_ind, face_contour_modify)
    face_contour_ind2 = KeypointsWithPose(pitch_ref, yaw, roll_ref, vertex, tri, 
                                          isoline_face_contour, face_contour_ind, face_contour_modify)
    face_contour_ind[adjust_ind] = face_contour_ind2[adjust_ind]
    face_contour_ref = ProjectVertex_ref[:, face_contour_ind]
    all_vertex_adjust = np.zeros(all_vertex_ref.shape)
    all_vertex_adjust[:, :face_contour_ref.shape[1]] = face_contour_ref

    # 5. Rotate other img contour
    # favor relationships on src
    src_seq = deepcopy(face_contour_modify)
    # face relationships on ref
    ref_seq = sorted(list(set(range(len(face_contour_ind))).difference(set(src_seq))))
    # 1 for solid anchor; 2 for src anchor; 3 for ref anchor
    anchor_flags = []

    for i in range(len(contlist_src)):
        flags = np.zeros(contlist_src[i].shape[1])
        if i == 0:
            # the face contour, all are solid anchors
            flags[:] = 1
        elif i == len(contlist_src)-1:
            # the image contour, all are src anchors
            flags[:] = 2
        else:
            # middle points
            flags[src_seq] = 2
            flags[ref_seq] = 3

        anchor_flags.append(flags)
    anchor_flags = np.hstack(anchor_flags)

    all_vertex_adjust = AnchorAdjustment_Rotate(
        all_vertex_src, all_vertex_ref, all_vertex_adjust, bg_tri, anchor_flags, img)

    counter = 0
    contlist_ref = []
    for i, item in enumerate(contlist_src):
        contlist_ref.append(all_vertex_adjust[:, counter:counter+item.shape[1]])
        counter += item.shape[1]  

    return contlist_ref, t3d_ref


def FaceFrontalizationMapping(mask, tri_ind, all_vertex_src, all_vertex_ref, all_tri, 
                              bg_tri_num, valid_tri_half, vertex_length, tri_length, sym_tri_list):
    height, width = mask.shape
    nChannels = 1
    all_ver_dim, all_ver_length = all_vertex_src.shape
    all_tri_dim, all_tri_length = all_tri.shape
    # From matlab index to C index
    # tri_ind = tri_ind - 1
    all_vertex_src = all_vertex_src - 1
    all_vertex_ref = all_vertex_ref - 1
    # all_tri = all_tri - 1
    # sym_tri_list = sym_tri_list - 1
    symlist_length = sym_tri_list.shape[1]

    # make sure they are F-contiguous
    if not mask.flags.f_contiguous:
        mask = mask.copy(order='F')

    if not tri_ind.flags.f_contiguous:
        tri_ind = tri_ind.copy(order='F')
    if tri_ind.dtype != np.float64:
        tri_ind = tri_ind.astype(np.float64)

    if not all_vertex_src.flags.f_contiguous:
        all_vertex_src = all_vertex_src.copy(order='F')
    if not all_vertex_ref.flags.f_contiguous:
        all_vertex_ref = all_vertex_ref.copy(order='F')

    if not all_tri.flags.f_contiguous:
        all_tri = all_tri.copy(order='F')
    if all_tri.dtype != np.float64:
        all_tri = all_tri.astype(np.float64)   

    if not valid_tri_half.flags.f_contiguous:
        valid_tri_half = valid_tri_half.copy(order='F')    
    if valid_tri_half.dtype != np.float64:
        valid_tri_half = valid_tri_half.astype(np.float64)   

    if not sym_tri_list.flags.f_contiguous:
        sym_tri_list = sym_tri_list.copy(order='F')
    if sym_tri_list.dtype != np.float64:
        sym_tri_list = sym_tri_list.astype(np.float64)       

    corres_map, corres_map_sym = pyFF.pyFaceFrontalizationMapping(
        mask, width, height, nChannels, tri_ind, all_vertex_src, all_vertex_ref, all_ver_dim, all_ver_length,
        all_tri, all_tri_dim, all_tri_length, bg_tri_num, valid_tri_half, vertex_length, tri_length,
        sym_tri_list, symlist_length)
    # corres_map = corres_map + 1
    # corres_map_sym = corres_map_sym + 1

    return corres_map, corres_map_sym


def FaceFrontalizationMappingNosym(mask, tri_ind, all_vertex_src, all_vertex_ref, all_tri, 
                                   bg_tri_num, valid_tri_half, vertex_length, tri_length):
    height, width = mask.shape
    nChannels = 1
    all_ver_dim, all_ver_length = all_vertex_src.shape
    all_tri_dim, all_tri_length = all_tri.shape
    # From matlab index to C index
    # tri_ind = tri_ind - 1
    all_vertex_src = all_vertex_src - 1
    all_vertex_ref = all_vertex_ref - 1
    # all_tri = all_tri - 1

    # make sure they are F-contiguous
    if not mask.flags.f_contiguous:
        mask = mask.copy(order='F')

    if not tri_ind.flags.f_contiguous:
        tri_ind = tri_ind.copy(order='F')
    if tri_ind.dtype != np.float64:
        tri_ind = tri_ind.astype(np.float64)

    if not all_vertex_src.flags.f_contiguous:
        all_vertex_src = all_vertex_src.copy(order='F')
    if not all_vertex_ref.flags.f_contiguous:
        all_vertex_ref = all_vertex_ref.copy(order='F')

    if not all_tri.flags.f_contiguous:
        all_tri = all_tri.copy(order='F')
    if all_tri.dtype != np.float64:
        all_tri = all_tri.astype(np.float64)   

    if not valid_tri_half.flags.f_contiguous:
        valid_tri_half = valid_tri_half.copy(order='F')    
    if valid_tri_half.dtype != np.float64:
        valid_tri_half = valid_tri_half.astype(np.float64)     

    corres_map = pyFF.pyFaceFrontalizationMappingNosym(
        mask, width, height, nChannels, tri_ind, 
        all_vertex_src, all_vertex_ref, all_ver_dim, all_ver_length,
        all_tri, all_tri_dim, all_tri_length, bg_tri_num,
        valid_tri_half, vertex_length, tri_length)

    return corres_map


def FaceFrontalizationFilling(img, corres_map):
    height, width, nChannels = img.shape
    # # From matlab index to C index
    # corres_map = corres_map - 1
    result = pyFF.pyFaceFrontalizationFilling(img, width, height, nChannels, corres_map)
    return result


def AlignPoints(p1, p2):
    d, n = p1.shape

    mu1 = np.mean(p1, axis=1)
    mu2 = np.mean(p2, axis=1)

    p1_0 = p1 - mu1[:,np.newaxis]
    p2_0 = p2 - mu2[:,np.newaxis]
    sigma1 = np.sum(p1_0**2) / n
    #sigma2 = np.sum(p2_0**2) / n

    K = p2_0.dot(p1_0.T) / n

    # Matlab's svd command returns U, S and V, 
    #  while numpy.linalg.svd returns U, the diagonal of S, and V^T
    [U, G, V] = np.linalg.svd(K)    
    G = np.diag(G)    
    
    S = np.eye(d)
    if np.linalg.det(K) < 0:
        S[d-1, d-1] = -1
        
    R = U.dot(S).dot(V)
    c = np.trace(G.dot(S)) / sigma1
    t = mu2 - c*R.dot(mu1)

    return c, R, t


def RotationMatrix2Angle(R):
# % reference: Extracting Euler Angles from a Rotation Matrix, Mike Day
# % if you are interested in this theme, please refer to 
# % http://www.mathworks.com/matlabcentral/newsreader/view_thread/160945
    theta1 = math.atan2(R[1,2], R[2,2])
    c2 = np.sqrt(R[0,0]**2 + R[0,1]**2)
    theta2 = math.atan2(-R[0,2], c2)
    s1 = np.sin(theta1)
    c1 = np.cos(theta1)
    theta3 = math.atan2(s1*R[2,0] - c1*R[1,0], c1*R[1,1] - s1*R[2,1])

    phi, gamma, theta = -theta1, -theta2, -theta3
    return phi, gamma, theta


def FittingShape3D(pt3d, f, R, t, mu, w, sigma, beta):
    # % Initialize Shape with Keypoint
    # % @input pt3d: Keypoint on the modal;
    # % @input pt2d: Keypoint on the image
    # % @input keypoints1: Keypoint index on the modal
    # % @input R t s: Pose parameter
    # % @input beta: Regularization parameter;
    # % @input sigma: Shape's PCA parameter sigma
    # % @output alpha: Shape's PCA paramter
    m = pt3d.shape[1]
    n = w.shape[1]
    t3d = t[:,np.newaxis]
    # t3d = repmat(t3d, 1, size(pt3d,2));

    s3d = mu.reshape((3,-1), order='F')
    s3d = f*R.dot(s3d)
    
    w3d = np.zeros((3*m, n))    
    for i in range(n):        
        tempdata = w[:,i].reshape((3,-1), order='F')
        tempdata3d = f*R.dot(tempdata) 
        w3d[:,i] = tempdata3d.ravel('F')

    # % optimize the equation
    # % fit 3D morphable model
    # % optimize ||x - T(w * alpha + mu)|| + lambda * alpha' * C * alpha
    # % (w'T'Tw + lambda*C) * alpha = w'T'x - w'T'T*mu, w2d = wT 
    equationLeft = w3d.T.dot(w3d) + beta*np.diag(1.0/(sigma**2))    
    equationRight = w3d.T.dot((pt3d-s3d-t3d).ravel('F'))
    alpha = np.linalg.lstsq(equationLeft, equationRight, rcond=None)[0]

    return alpha


def FittingShape3D_v2(pt3d, f, R, t, mu, w, sigma, beta):
    # % Initialize Shape with Keypoint
    # % @input pt3d: Keypoint on the modal;
    # % @input pt2d: Keypoint on the image
    # % @input keypoints1: Keypoint index on the modal
    # % @input R t s: Pose parameter
    # % @input beta: Regularization parameter;
    # % @input sigma: Shape's PCA parameter sigma
    # % @output alpha: Shape's PCA paramter
    m = pt3d.shape[1]    
    t3d = t[:,np.newaxis]

    # note that mu is (3, n_points), w is (3,n_point*num_components). 
    s3d = f*R.dot(mu)    
    w3d = f*R.dot(w).reshape((3*m,-1), order='F')     
    
    # % optimize the equation
    # % fit 3D morphable model
    # % optimize ||x - T(w * alpha + mu)|| + lambda * alpha' * C * alpha
    # % (w'T'Tw + lambda*C) * alpha = w'T'x - w'T'T*mu, w2d = wT 
    equationLeft = w3d.T.dot(w3d) + beta*np.diag(1.0/(sigma**2))    
    equationRight = w3d.T.dot((pt3d-s3d-t3d).ravel('F'))
    alpha = np.linalg.lstsq(equationLeft, equationRight, rcond=None)[0]

    return alpha    


def FittingModel3D_validpoint(pt3d, Model, valid_ind):
    iteration = 0
    maxiteration = 4

    mu = np.squeeze(Model['mu'][0,0])
    w = Model['w'][0,0]
    sigma = np.squeeze(Model['sigma'][0,0])
    # tri = Model['tri'][0,0]

    keypoints1 = np.vstack([3*valid_ind, 3*valid_ind+1, 3*valid_ind+2])
    keypoints1 = keypoints1.ravel('F')

    alpha = np.zeros(w.shape[1])
    f, R, t = 1, np.eye(3), np.zeros(3)

    mu_key = mu[keypoints1]
    mu_key_rs = mu_key.reshape((3,-1), order='F')

    w_key = w[keypoints1]        
    w_key_rs = w_key.reshape((3,-1), order='F')   

    # Firstly pose and expression
    while True:
        if iteration > maxiteration:
            break

        iteration += 1

        # 1. Pose Estimate  
        vertex_key = mu_key + w_key.dot(alpha)    
        vertex_key = vertex_key.reshape((3,-1), order='F')

        f, R, t = AlignPoints(vertex_key, pt3d)

        # 2.shape fitting
        beta = 3000
        # alpha = FittingShape3D(pt3d, f, R, t, mu_key, w_key, sigma, beta)
        alpha = FittingShape3D_v2(pt3d, f, R, t, mu_key_rs, w_key_rs, sigma, beta)

    phi, gamma, theta = RotationMatrix2Angle(R) 

    return f, phi, gamma, theta, t, alpha


def ModelCompletionBFM(ProjectVertex, tri, model_fullhead, model_completion):    
    muf  = np.squeeze(model_fullhead['mu'][0,0])
    wf   = model_fullhead['w'][0,0]
    trif = model_fullhead['tri'][0,0] - 1

    indf_c = np.squeeze(model_completion['indf_c'].astype(np.int)) - 1
    indf_c2b = np.squeeze(model_completion['indf_c2b'].astype(np.int)) - 1
    trif_stitch = model_completion['trif_stitch'].astype(np.int) - 1
    trif_backhead = model_completion['trif_backhead'].astype(np.int) - 1

    ProjectVertex_c2b = ProjectVertex[:, indf_c2b]

    f, phi, gamma, theta, t, alpha = FittingModel3D_validpoint(ProjectVertex_c2b, model_fullhead, indf_c)
    
    vertexf = muf + wf.dot(alpha)
    vertexf = vertexf.reshape((3,-1), order='F')
    ProjectVertexf = f*RotationMatrix(phi, gamma, theta, False).dot(vertexf) + t[:,np.newaxis]

    ProjectVertex_full = np.hstack([ProjectVertex, ProjectVertexf])
    tri_full = np.hstack([tri, trif_backhead, trif_stitch])

    # blend
    iteration = 1

    vertex_blend = deepcopy(ProjectVertex_full)
    stitch_point = np.unique(trif_stitch)

    for _ in range(iteration):    
        vertex_temp = deepcopy(vertex_blend)
        for i in range(len(stitch_point)):
            ind = stitch_point[i] # blur the ith ind        
            conn_tri = np.any(tri_full == ind, axis=0)         
            conn_tri = tri_full[:, conn_tri]
            conn_point = np.unique(conn_tri)
            vertex_temp[:,ind] = np.mean(vertex_blend[:,conn_point], axis=1)    
        vertex_blend = deepcopy(vertex_temp)

    ProjectVertex_full = vertex_blend

    return ProjectVertex_full, tri_full     


def PrecomputeConnPoint(tri, model_completion):
    trif_stitch = model_completion['trif_stitch'].astype(np.int) - 1
    trif_backhead = model_completion['trif_backhead'].astype(np.int) - 1
    tri_full = np.hstack([tri, trif_backhead, trif_stitch])

    stitch_point = np.unique(trif_stitch)  
    
    conn_point_info = {'stitch_point': stitch_point, 'tri_full': tri_full}        
    conn_point_info['dict'] = defaultdict(lambda: [])
    for ind in stitch_point:
        # blur the ith ind
        conn_tri = np.any(tri_full == ind, axis=0)         
        conn_tri = tri_full[:, conn_tri]            
        conn_point = np.unique(conn_tri)
        conn_point_info['dict'][ind] = conn_point
    
    return conn_point_info


def ModelCompletionBFM_v2(ProjectVertex, model_fullhead, model_completion, conn_point_info):
    muf  = np.squeeze(model_fullhead['mu'][0,0])
    wf   = model_fullhead['w'][0,0]
    # trif = model_fullhead['tri'][0,0] - 1

    indf_c = np.squeeze(model_completion['indf_c'].astype(np.int)) - 1
    indf_c2b = np.squeeze(model_completion['indf_c2b'].astype(np.int)) - 1
    #     trif_stitch = model_completion['trif_stitch'].astype(np.int) - 1
    #     trif_backhead = model_completion['trif_backhead'].astype(np.int) - 1

    ProjectVertex_c2b = ProjectVertex[:, indf_c2b]

    f, phi, gamma, theta, t, alpha = FittingModel3D_validpoint(ProjectVertex_c2b, model_fullhead, indf_c)
    
    vertexf = muf + wf.dot(alpha)
    vertexf = vertexf.reshape((3,-1), order='F')
    ProjectVertexf = f*RotationMatrix(phi, gamma, theta, False).dot(vertexf) + t[:,np.newaxis]

    ProjectVertex_full = np.hstack([ProjectVertex, ProjectVertexf])
    #     tri_full = np.hstack([tri, trif_backhead, trif_stitch])    
    tri_full = conn_point_info['tri_full']
    
    # blend
    iteration = 1

    vertex_blend = deepcopy(ProjectVertex_full)
    #     stitch_point = np.unique(trif_stitch)
    stitch_point = conn_point_info['stitch_point']
        
    for _ in range(iteration):    
        vertex_temp = deepcopy(vertex_blend)
        for ind in stitch_point:
            # blur the i_th ind    
            conn_point = conn_point_info['dict'][ind]
            vertex_temp[:,ind] = np.mean(vertex_blend[:,conn_point], axis=1)      
        vertex_blend = deepcopy(vertex_temp)

    ProjectVertex_full = vertex_blend        

    return ProjectVertex_full, tri_full


def calc_barycentric_coordinates(pt, vertices, tri_list):
    a = vertices[tri_list[:, 0]]
    b = vertices[tri_list[:, 1]]
    c = vertices[tri_list[:, 2]]
    v0, v1 = b - a, c - a
    v2 = np.expand_dims(pt, axis=0).repeat(a.shape[0], axis=0) - a
    d00 = (v0 * v0).sum(axis=1)
    d01 = (v0 * v1).sum(axis=1)
    d11 = (v1 * v1).sum(axis=1)
    d20 = (v2 * v0).sum(axis=1)
    d21 = (v2 * v1).sum(axis=1)
    denom = d00 * d11 - d01 * d01
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    return np.vstack((u, v, w)).T
