import torch
import os
import sys
from torch import nn


sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../")))

from algorithms.BaseClientTrainer import BaseClientTrainer

from train_tools.preprocessing.cifar10.loader import get_dataloader_cifar10
from train_tools.preprocessing.cifar100.loader import get_dataloader_cifar100
from train_tools.preprocessing.tinyimagenet.loader import get_dataloader_tinyimagenet
from train_tools.preprocessing.imagenet.loader import get_dataloader_imagenet

__all__ = ["ClientTrainer"]

DATA_LOADERS = {
    "cifar10": get_dataloader_cifar10,
    "cifar100": get_dataloader_cifar100,
    "tinyimagenet": get_dataloader_tinyimagenet,
    "imagenet": get_dataloader_imagenet
    
}



class ClientTrainer(BaseClientTrainer):
    def __init__(self, **kwargs):
        super(ClientTrainer, self).__init__(**kwargs)
        """
        ClientTrainer class contains local data and local-specific information.
        After local training, upload weights to the Server.
        """
    
    def download_global(self, server_weights, server_optimizer):
        """Load model & Optimizer"""
        self.model.load_state_dict(server_weights)

        server_optimizer_info=server_optimizer['param_groups'][0]
    
        body_params = [p for name, p in self.model.named_parameters() if 'classifier' not in name]
        head_params = [p for name, p in self.model.named_parameters() if 'classifier' in name]
    
        self.optimizer= torch.optim.SGD([{'params': body_params, 'lr': server_optimizer_info['lr']},
                                     {'params': head_params, 'lr': 0}],
                                    momentum=server_optimizer_info['momentum'],
                                    weight_decay=server_optimizer_info['weight_decay'])
    
    
    def one_hot_encoding(self, num_class, target_batch):
        # num_class: 클래스의 개수
        # target_batch: 배치 크기(batch_size)의 리스트로, 각 원소는 0부터 num_class - 1 사이의 정수

        # 배치 크기 확인
        batch_size = len(target_batch)

        # one-hot 벡터를 담을 텐서 초기화 (크기: [batch_size, num_class])
        one_hot_vectors = torch.zeros(batch_size, num_class)

        # target_batch의 각 요소에 대해 해당하는 인덱스를 1로 설정하여 one-hot 벡터 생성
        for i, target in enumerate(target_batch):
            one_hot_vectors[i, target] = 1

        return one_hot_vectors
    


    def train(self):
        """Local training"""
        self.model.train()
        self.model.to(self.device)
        
        local_size = self.datasize
        
        epoch_loss = []
        
        root = os.path.join("./data", self.data_name)
        self.trainloader=DATA_LOADERS[self.data_name](root=root, train=True, batch_size=self.batch_size, dataidxs=self.train_idxs)
        self.cls_weight=self.class_frequency*(len(self.class_frequency)/self.class_frequency.sum().item()) 
        
        
        if self.test_idxs is None: #LDA Setting
            for _ in range(self.average_iteration*self.local_epochs):
                dataiter = iter(self.trainloader)
                data, targets = next(dataiter)

                self.optimizer.zero_grad()

                # forward pass
                data, targets = data.to(self.device), targets.to(self.device)
                output = self.model(data)*self.cls_weight
                loss = self.criterion(output, targets)
                
                # backward pass
                loss.backward()

                self.optimizer.step()
                
        else: #Sharding Setting
            for _ in range(self.local_epochs):
                batch_loss=[]
                for data, targets in self.trainloader:
                    self.optimizer.zero_grad()

                    # forward pass
                    data, targets = data.to(self.device), targets.to(self.device)
                    output = self.model(data)*self.cls_weight
                    
                    loss = self.criterion(output, targets)

                    # backward pass
                    loss.backward()

                    self.optimizer.step()
                    
                    batch_loss.append(loss.item())
                epoch_loss.append(sum(batch_loss)/len(batch_loss))

        local_results = self._get_local_stats()
        
    
        return local_results, local_size
    