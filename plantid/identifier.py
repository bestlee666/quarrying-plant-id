import os
from collections import OrderedDict

import cv2
import numpy as np
from . import utils


class PlantIdentifier(object):
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        model_filename = os.path.join(current_dir, 'models/quarrying_plantid_model.onnx')
        label_map_filename = os.path.join(current_dir, 'models/quarrying_plantid_label_map.txt')
        self.net = cv2.dnn.readNetFromONNX(model_filename)
        self.label_name_dict = self._get_label_name_dict(label_map_filename)
        self.family_dict, self.genus_dict = self._get_family_and_genus_dict(label_map_filename)
        
    @staticmethod
    def _get_label_name_dict(filename):
        records = utils.load_list(filename)
        label_name_dict = {}
        for record in records:
            label, chinese_name, latin_name = record.split(',')
            label_name_dict[int(label)] = OrderedDict([('chinese_name', chinese_name), 
                                                       ('latin_name', latin_name)])
        return label_name_dict
        
    @staticmethod
    def _get_family_and_genus_dict(filename):
        records = utils.load_list(filename)
        family_dict, genus_dict = {}, {}
        for record in records:
            label, chinese_name, latin_name = record.split(',')
            underscore_parts = chinese_name.split('_')
            if len(underscore_parts) >= 1 and underscore_parts[0].endswith('科'):
                family_name = underscore_parts[0]
                family_dict.setdefault(family_name, []).append(int(label))
            if len(underscore_parts) >= 2:
                genus_name = underscore_parts[1]
                genus_dict.setdefault(genus_name, []).append(int(label))
        return family_dict, genus_dict
        
    @staticmethod
    def _get_collective_probs(probs, collective_dict):
        batch_size = len(probs)
        num_collective = len(collective_dict)
        collective_probs = np.empty((batch_size, num_collective), dtype=probs.dtype)
        for batch_ind in range(batch_size):
            for collective_ind, collective_name in enumerate(collective_dict):
                taxon_indices = collective_dict[collective_name]
                collective_prob = sum(probs[batch_ind, index] for index in taxon_indices)
                collective_probs[batch_ind, collective_ind] = collective_prob
        collective_names = list(collective_dict.keys())
        return collective_probs, collective_names
        
    @staticmethod
    def _preprocess(image):
        try:
            image = utils.normalize_image_shape(image)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            image = utils.resize_image_short(image, 320)
            image = utils.center_crop(image, 299, 299)
            image = image.astype(np.float32)
            image /= 255.0
            image -= np.asarray([0.485, 0.456, 0.406])
            image /= np.asarray([0.229, 0.224, 0.225])
            image = np.transpose(image, (2,0,1))
            image = np.expand_dims(image, axis=0)
            return image
        except:
            return None
        
    def predict(self, image, topk=5):
        results, family_results, genus_results = [], [], []
        
        inputs = self._preprocess(image)
        if inputs is None:
            return {"status": -1, "message": "Inference preprocess error.", 
                    "results": results, "family_results": family_results,
                    "genus_results": genus_results}
        
        try:
            self.net.setInput(inputs)
            logits = self.net.forward()
            probs = utils.softmax(logits)
        except:
             return {"status": -2, "message": "Inference error.", 
                     "results": results, "family_results": family_results,
                     "genus_results": genus_results}

        topk_probs, topk_indices = utils.find_topk(probs, topk)
        for ind, prob in zip(topk_indices[0], topk_probs[0]):
            one_result = self.label_name_dict[ind]
            one_result['probability'] = prob
            results.append(one_result)

        family_probs, family_names = self._get_collective_probs(probs, self.family_dict)
        family_topk_probs, family_topk_indices = utils.find_topk(family_probs, topk)
        for ind, prob in zip(family_topk_indices[0], family_topk_probs[0]):
            one_result = OrderedDict()
            one_result['chinese_name'] = family_names[ind]
            one_result['latin_name'] = ''
            one_result['probability'] = prob
            family_results.append(one_result)
            
        genus_probs, genus_names = self._get_collective_probs(probs, self.genus_dict)
        genus_topk_probs, genus_topk_indices = utils.find_topk(genus_probs, topk)
        for ind, prob in zip(genus_topk_indices[0], genus_topk_probs[0]):
            one_result = OrderedDict()
            one_result['chinese_name'] = genus_names[ind]
            one_result['latin_name'] = ''
            one_result['probability'] = prob
            genus_results.append(one_result)
            
        return {"status": 0, "message": "OK", 
                "results": results, "family_results": family_results,
                "genus_results": genus_results}
                
