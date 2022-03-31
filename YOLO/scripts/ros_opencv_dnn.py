#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Mon April 19 20:58:03 2021
@author: mason
"""

''' import libraries '''
import cv2
import time
import rospy
import signal
import sys

from sensor_msgs.msg import Image
from sensor_msgs.msg import CompressedImage
from cv_bridge import CvBridge, CvBridgeError
from yolo_ros_simple.msg import bbox, bboxes

def signal_handler(signal, frame): # ctrl + c -> exit program
        print('You pressed Ctrl+C!')
        sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)


class cv_yolo_ros():
    def __init__(self):
        rospy.init_node('cv_yolo_ros_node', anonymous=True)
        self.flag = False
        self.inference_rate = rospy.get_param("~inference_rate", 30)
        self.img_in_topic = rospy.get_param("~img_in_topic", "/d435i/depth/rgb_image_raw")
        self.img_out_topic = rospy.get_param("~img_out_topic", "/detected")
        self.bbox_out_topic = rospy.get_param("/bbox_out_topic", "/bboxes")

        self.confidence_threshold = rospy.get_param("~confidence_threshold", 0.8)
        self.nms_threshold = rospy.get_param("~nms_threshold", 0.4)

        self.class_file = rospy.get_param("~class_file", "obj.names")
        self.weight_file = rospy.get_param("~weight_file", "yolov4-tiny-3l-uav_final.weights")
        self.cfg_file = rospy.get_param("~cfg_file", "yolov4-tiny-3l-uav.cfg")

        self.backend = rospy.get_param("~backend", cv2.dnn.DNN_BACKEND_CUDA)
    ### cv2.dnn.DNN_BACKEND_CUDA for GPU, 
    ### cv2.dnn.DNN_BACKEND_OPENCV for CPU
    ### cv2.dnn.DNN_BACKEND_INFERENCE_ENGINE for OpenVINO
        self.target = rospy.get_param("~target", cv2.dnn.DNN_TARGET_CUDA)
    ### Either DNN_TARGET_CUDA_FP16 or DNN_TARGET_CUDA must be enabled for GPU
    ### cv2.dnn.DNN_TARGET_CPU for CPU or OpenVINO

        self.net=cv2.dnn.readNet(self.weight_file, self.cfg_file)
        self.net.setPreferableBackend(self.backend)
        self.net.setPreferableTarget(self.target)

        self.img_subscriber = rospy.Subscriber(self.img_in_topic, Image, self.img_callback)
        self.img_publisher = rospy.Publisher(self.img_out_topic, Image, queue_size=1)
        self.box_publisher = rospy.Publisher(self.bbox_out_topic, bboxes, queue_size=1)
        self.bridge = CvBridge()
        self.rate = rospy.Rate(self.inference_rate)

        self.class_names = []
        with open(self.class_file, "r") as f:
            self.class_names = [cname.strip() for cname in f.readlines()]

        self.model = cv2.dnn_DetectionModel(self.net)
        self.model.setInputParams(size=(640, 480), scale=1/float(255.0), swapRB=True)

    def img_callback(self, msg):
        self.img_cb_in = msg
        # self.img_cb_in = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        self.flag = True



if __name__=='__main__':
    COLORS = [(0, 255, 0), (255, 255, 0), (0, 255, 0), (255, 0, 0)]
    avg_FPS=0; count=0; total_fps=0;
    cyr=cv_yolo_ros()
    print("Start operating YOLO!")
    while 1:
        try:
            if cyr.flag:
                start = time.time()
                # frame = cyr.img_cb_in #temporal backup
                header = cyr.img_cb_in.header
                frame = cyr.bridge.imgmsg_to_cv2(cyr.img_cb_in, "bgr8")
                classes, scores, boxes = cyr.model.detect(frame, cyr.confidence_threshold, cyr.nms_threshold)
                end = time.time()
                FPS = 1 / (end - start)
                total_fps = total_fps + FPS; count=count+1;
                avg_FPS = total_fps / float(count)

                out_boxes = bboxes()
                out_boxes.header = header
                start_drawing = time.time()
                for (classid, score, box) in zip(classes, scores, boxes):
                    out_box = bbox()
                    out_box.score = score[0] # score
                    out_box.x = box[0]
                    out_box.y = box[1]
                    out_box.width = box[2]
                    out_box.height = box[3]
                    out_box.crop = cyr.bridge.cv2_to_imgmsg(frame[box[1]:box[1]+box[3], box[0]:box[0]+box[2], :], "bgr8")
                    out_box.id = classid[0] # classid
                    out_box.Class = cyr.class_names[classid[0]] # classid
                    out_boxes.bboxes.append(out_box)
                    color = COLORS[int(classid) % len(COLORS)]
                    label = "%s : %f" % (cyr.class_names[classid[0]], score) # classid
                    cv2.rectangle(frame, box, color, 5)
                    cv2.putText(frame, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                end_drawing = time.time()

                fps_label = "avg FPS: %.2f FPS: %.2f (excluding drawing %.2fms)" % (avg_FPS, 1 / (end - start), (end_drawing - start_drawing) * 1000)
                cv2.putText(frame, fps_label, (0, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 127), 2)
                #print(fps_label)
                img=cyr.bridge.cv2_to_imgmsg(frame, "bgr8")
                img.header.stamp = rospy.Time.now()
                cyr.img_publisher.publish(img)
                cyr.box_publisher.publish(out_boxes)
            cyr.rate.sleep()
        except (rospy.ROSInterruptException, SystemExit, KeyboardInterrupt) :
            # print(avg_FPS)
            sys.exit(0)
