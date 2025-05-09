from args import args
import torch
import torch.nn as nn
import models
from utils import *

from AGRs import *
from Attacks import *

import copy
import numpy as np
import torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from collections import defaultdict
import collections


#####################################FRL#########################################
def FRL_train(tr_loaders, te_loader):
    print ("#########Federated Learning using Rankings############")
    args.conv_type = 'MaskConv'
    args.conv_init = 'signed_constant'
    args.bn_type="NonAffineNoStatsBN"    
    
    n_attackers = int(args.nClients * args.at_fractions)
    sss = "fraction of maliciou clients: %.2f | total number of malicious clients: %d | attack type: %s"%(args.at_fractions,
                                                                                        n_attackers, args.attack_type)
    print (sss)
    with (args.run_base_dir / "output.txt").open("a") as f:
        f.write("\n"+str(sss))
    
    criterion = nn.CrossEntropyLoss().to(args.device)
    FLmodel = getattr(models, args.model)().to(args.device)
    
    initial_scores={}
    for n, m in FLmodel.named_modules():
        if hasattr(m, "scores"):
            initial_scores[str(n)]=m.scores.detach().clone().flatten().sort()[0]
    
    e=0
    t_best_acc=0
    while e <= args.FL_global_epochs:
        torch.cuda.empty_cache() 
        round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
        round_malicious = round_users[round_users < n_attackers]
        round_benign = round_users[round_users >= n_attackers]
        while len(round_malicious)>=args.round_nclients/2:
            round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
            round_malicious = round_users[round_users < n_attackers]
            round_benign = round_users[round_users >= n_attackers]
            
        user_updates=collections.defaultdict(list)
        ########################################benign Client Learning#########################################
        for kk in round_benign:
            mp = copy.deepcopy(FLmodel)
            optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)
            
            scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
            for epoch in range(args.local_epochs):
                train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                scheduler.step()

            for n, m in mp.named_modules():
                    if hasattr(m, "scores"):
                        rank=Find_rank(m.scores.detach().clone())
                        user_updates[str(n)]=rank[None,:] if len(user_updates[str(n)]) == 0 else torch.cat((user_updates[str(n)], rank[None,:]), 0)
                        del rank
            del optimizer, mp, scheduler
        ########################################malicious Client Learning######################################
        if len(round_malicious):
            sum_args_sorts_mal={}
            for kk in np.random.choice(n_attackers, min(n_attackers, args.rand_mal_clients), replace=False):
                torch.cuda.empty_cache()  
                mp = copy.deepcopy(FLmodel)
                optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)
                scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
                for epoch in range(args.local_epochs):
                    train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                    scheduler.step()

                for n, m in mp.named_modules():
                    if hasattr(m, "scores"):
                        rank=Find_rank(m.scores.detach().clone())
                        rank_arg=torch.sort(rank)[1]
                        if str(n) in sum_args_sorts_mal:
                            sum_args_sorts_mal[str(n)]+=rank_arg
                        else:
                            sum_args_sorts_mal[str(n)]=rank_arg
                        del rank, rank_arg
                del optimizer, mp, scheduler

            for n, m in FLmodel.named_modules():
                if hasattr(m, "scores"):
                    if args.attack_type == "torch_sort":
                        rank_mal_agr = torch.sort(sum_args_sorts_mal[str(n)], descending=True)[1]
                    elif args.attack_type == "circular_rotation":
                        rank_mal_agr = circular_rotation(sum_args_sorts_mal[str(n)])
                    elif args.attack_type == "reverse_firsthalf_rotation":
                        rank_mal_agr = reverse_firsthalf_rotation(sum_args_sorts_mal[str(n)])
                    elif args.attack_type == "reverse_first_secondhalf_rotation":
                        rank_mal_agr = reverser_middle_firsthalf_rotation(sum_args_sorts_mal[str(n)])
                    for kk in round_malicious:
                        user_updates[str(n)]=rank_mal_agr[None,:] if len(user_updates[str(n)]) == 0 else torch.cat((user_updates[str(n)], rank_mal_agr[None,:]), 0)
            del sum_args_sorts_mal
        ########################################Server AGR#########################################
        FRL_Vote(FLmodel, user_updates, initial_scores)
        del user_updates
        if (e+1)%1==0:
            t_loss, t_acc = test(te_loader, FLmodel, criterion, args.device) 
            if t_acc>t_best_acc:
                t_best_acc=t_acc

            sss='e %d | malicious users: %d | test acc %.4f test loss %.6f best test_acc %.4f' % (e, len(round_malicious), t_acc, t_loss, t_best_acc)
            print (sss)
            with (args.run_base_dir / "output.txt").open("a") as f:
                f.write("\n"+str(sss))
        e+=1
        
def circular_rotation(rank):
    middle = len(rank)//2
    return torch.cat((rank[middle:], rank[:middle]))

def reverse_firsthalf_rotation(rank):
    middle = len(rank)//2
    first_half_reversed = rank[:middle].flip(0)
    return torch.cat((rank[middle:],first_half_reversed))

def reverser_middle_firsthalf_rotation(rank):
    middle = len(rank)//2
    first_half = rank[:middle]
    first_half_middle = len (first_half)//2
    first_of_first_half = first_half[:first_half_middle]
    second_of_first_half = first_half[first_half_middle:]
    second_half = rank[middle:]
    return torch.cat((second_half, first_of_first_half, second_of_first_half.flip(0)))

#####################################FedAVG#########################################
def FedAVG(tr_loaders, te_loader):
    print ("#########Federated Learning using FedAVG############")
    args.conv_type = 'StandardConv'
    args.bn_type="NonAffineNoStatsBN"    
    
    n_attackers = int(args.nClients * args.at_fractions)
    sss = "fraction of maliciou clients: %.2f | total number of malicious clients: %d"%(args.at_fractions,
                                                                                        n_attackers)
    print (sss)
    with (args.run_base_dir / "output.txt").open("a") as f:
        f.write("\n"+str(sss))
    
    criterion = nn.CrossEntropyLoss().to(args.device)
    FLmodel = getattr(models, args.model)().to(args.device)
    
    model_received = []
    for i, (name, param) in enumerate(FLmodel.state_dict().items()):
        model_received = param.view(-1).data.type(torch.cuda.FloatTensor) if len(model_received) == 0 else torch.cat((model_received, param.view(-1).data.type(torch.cuda.FloatTensor)))
    
    e=0
    t_best_acc=0
    while e <= args.FL_global_epochs:
        torch.cuda.empty_cache() 
        round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
        round_malicious = round_users[round_users < n_attackers]
        round_benign = round_users[round_users >= n_attackers]
        while len(round_malicious)>=args.round_nclients/2:
            round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
            round_malicious = round_users[round_users < n_attackers]
            round_benign = round_users[round_users >= n_attackers]
            
        user_updates = []
        ########################################benign Client Learning#########################################
        for kk in round_benign:
            mp = copy.deepcopy(FLmodel)
            optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)
            
            scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
            for epoch in range(args.local_epochs):
                train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                scheduler.step()
                
                
            params = []
            for i, (name, param) in enumerate(mp.state_dict().items()):
                params = param.view(-1).data.type(torch.cuda.FloatTensor) if len(params) == 0 else torch.cat((params, param.view(-1).data.type(torch.cuda.FloatTensor)))

            update =  (params - model_received)

            user_updates = update[None,:] if len(user_updates) == 0 else torch.cat((user_updates, update[None,:]), 0)

            del optimizer, mp, scheduler
        ########################################malicious Client Learning######################################
        for kk in round_malicious:
            scale=100000
            mal_update = scale * model_received
            user_updates = mal_update[None,:] if len(user_updates) == 0 else torch.cat((user_updates, mal_update[None,:]), 0)

        ########################################Server AGR#########################################
        agg_update = torch.mean(user_updates, dim=0)
        del user_updates
        model_received = model_received + agg_update
        FLmodel = getattr(models, args.model)().to(args.device)
        start_idx=0
        state_dict = {}
        previous_name = 'none'
        for i, (name, param) in enumerate(FLmodel.state_dict().items()):
            start_idx = 0 if i == 0 else start_idx + len(FLmodel.state_dict()[previous_name].data.view(-1))
            start_end = start_idx + len(FLmodel.state_dict()[name].data.view(-1))
            params = model_received[start_idx:start_end].reshape(FLmodel.state_dict()[name].data.shape)
            state_dict[name] = params
            previous_name = name

        FLmodel.load_state_dict(state_dict)
        
        if (e+1)%1==0:
            t_loss, t_acc = test(te_loader, FLmodel, criterion, args.device) 
            
            if t_acc>t_best_acc:
                t_best_acc=t_acc

            sss='e %d | malicious users: %d | test acc %.4f test loss %.6f best test_acc %.4f' % (e, len(round_malicious), t_acc, t_loss, t_best_acc)
            print (sss)
            with (args.run_base_dir / "output.txt").open("a") as f:
                f.write("\n"+str(sss))
                
            if math.isnan(t_loss) or t_loss > 10000:
                print('val loss %f... exit: The global model is totally destroyed by the adversary' % t_loss)
                break
        e+=1
        
#######################################Trimmed-Mean######################################
def Tr_Mean(tr_loaders, te_loader):
    print ("#########Federated Learning using Trimmed Mean############")
    args.conv_type = 'StandardConv'
    args.bn_type="NonAffineNoStatsBN"    
    
    n_attackers = int(args.nClients * args.at_fractions)
    sss = "fraction of maliciou clients: %.2f | total number of malicious clients: %d"%(args.at_fractions,
                                                                                        n_attackers)
    print (sss)
    with (args.run_base_dir / "output.txt").open("a") as f:
        f.write("\n"+str(sss))
    
    criterion = nn.CrossEntropyLoss().to(args.device)
    FLmodel = getattr(models, args.model)().to(args.device)
    
    model_received = []
    for i, (name, param) in enumerate(FLmodel.state_dict().items()):
        model_received = param.view(-1).data.type(torch.cuda.FloatTensor) if len(model_received) == 0 else torch.cat((model_received, param.view(-1).data.type(torch.cuda.FloatTensor)))
    
    e=0
    t_best_acc=0
    while e <= args.FL_global_epochs:
        torch.cuda.empty_cache() 
        round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
        round_malicious = round_users[round_users < n_attackers]
        round_benign = round_users[round_users >= n_attackers]
        while len(round_malicious)>=args.round_nclients/2:
            round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
            round_malicious = round_users[round_users < n_attackers]
            round_benign = round_users[round_users >= n_attackers]
            
        user_updates = []
        ########################################benign Client Learning#########################################
        for kk in round_benign:
            mp = copy.deepcopy(FLmodel)
            optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)
            
            scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
            for epoch in range(args.local_epochs):
                train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                scheduler.step()
                
                
            params = []
            for i, (name, param) in enumerate(mp.state_dict().items()):
                params = param.view(-1).data.type(torch.cuda.FloatTensor) if len(params) == 0 else torch.cat((params, param.view(-1).data.type(torch.cuda.FloatTensor)))

            update =  (params - model_received)

            user_updates = update[None,:] if len(user_updates) == 0 else torch.cat((user_updates, update[None,:]), 0)

            del optimizer, mp, scheduler
        ########################################malicious Client Learning######################################
        if len(round_malicious):
            mal_updates = []
            for kk in np.random.choice(n_attackers, min(n_attackers, args.rand_mal_clients), replace=False):
                mp = copy.deepcopy(FLmodel)
                optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)

                scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
                for epoch in range(args.local_epochs):
                    train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                    scheduler.step()


                params = []
                for i, (name, param) in enumerate(mp.state_dict().items()):
                    params = param.view(-1).data.type(torch.cuda.FloatTensor) if len(params) == 0 else torch.cat((params, param.view(-1).data.type(torch.cuda.FloatTensor)))

                update =  (params - model_received)

                mal_updates = update[None,:] if len(mal_updates) == 0 else torch.cat((mal_updates, update[None,:]), 0)

                del optimizer, mp, scheduler
                
            mal_update = our_attack_trmean(mal_updates, len(round_malicious), dev_type='std', threshold=5.0)
            del mal_updates

            for kk in round_malicious:
                user_updates = mal_update[None,:] if len(user_updates) == 0 else torch.cat((user_updates, mal_update[None,:]), 0)
        ########################################Server AGR#########################################
        agg_update = tr_mean(user_updates, len(round_malicious))
        del user_updates
        model_received = model_received + agg_update
        FLmodel = getattr(models, args.model)().to(args.device)
        start_idx=0
        state_dict = {}
        previous_name = 'none'
        for i, (name, param) in enumerate(FLmodel.state_dict().items()):
            start_idx = 0 if i == 0 else start_idx + len(FLmodel.state_dict()[previous_name].data.view(-1))
            start_end = start_idx + len(FLmodel.state_dict()[name].data.view(-1))
            params = model_received[start_idx:start_end].reshape(FLmodel.state_dict()[name].data.shape)
            state_dict[name] = params
            previous_name = name

        FLmodel.load_state_dict(state_dict)
        
        if (e+1)%1==0:
            t_loss, t_acc = test(te_loader, FLmodel, criterion, args.device) 
            if math.isnan(t_loss) or t_loss > 10000:
                print('val loss %f... exit: The global model is totally destroyed by the adversary' % val_loss)
                break
            if t_acc>t_best_acc:
                t_best_acc=t_acc

            sss='e %d | malicious users: %d | test acc %.4f test loss %.6f best test_acc %.4f' % (e, len(round_malicious), t_acc, t_loss, t_best_acc)
            print (sss)
            with (args.run_base_dir / "output.txt").open("a") as f:
                f.write("\n"+str(sss))
        e+=1
        
        
        
############################Multi-Krum#########################################
def Mkrum(tr_loaders, te_loader):
    print ("#########Federated Learning using Multi-Krum############")
    args.conv_type = 'StandardConv'
    args.bn_type="NonAffineNoStatsBN"    
    
    n_attackers = int(args.nClients * args.at_fractions)
    sss = "fraction of maliciou clients: %.2f | total number of malicious clients: %d"%(args.at_fractions,
                                                                                        n_attackers)
    print (sss)
    with (args.run_base_dir / "output.txt").open("a") as f:
        f.write("\n"+str(sss))
    
    criterion = nn.CrossEntropyLoss().to(args.device)
    FLmodel = getattr(models, args.model)().to(args.device)
    
    model_received = []
    for i, (name, param) in enumerate(FLmodel.state_dict().items()):
        model_received = param.view(-1).data.type(torch.cuda.FloatTensor) if len(model_received) == 0 else torch.cat((model_received, param.view(-1).data.type(torch.cuda.FloatTensor)))
    
    e=0
    t_best_acc=0
    while e <= args.FL_global_epochs:
        torch.cuda.empty_cache() 
        round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
        round_malicious = round_users[round_users < n_attackers]
        round_benign = round_users[round_users >= n_attackers]
        while len(round_malicious)>=args.round_nclients/2:
            round_users = np.random.choice(args.nClients, args.round_nclients, replace=False)
            round_malicious = round_users[round_users < n_attackers]
            round_benign = round_users[round_users >= n_attackers]
            
        user_updates = []
        ########################################benign Client Learning#########################################
        for kk in round_benign:
            mp = copy.deepcopy(FLmodel)
            optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)
            
            scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
            for epoch in range(args.local_epochs):
                train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                scheduler.step()
                
                
            params = []
            for i, (name, param) in enumerate(mp.state_dict().items()):
                params = param.view(-1).data.type(torch.cuda.FloatTensor) if len(params) == 0 else torch.cat((params, param.view(-1).data.type(torch.cuda.FloatTensor)))

            update =  (params - model_received)

            user_updates = update[None,:] if len(user_updates) == 0 else torch.cat((user_updates, update[None,:]), 0)

            del optimizer, mp, scheduler
        ########################################malicious Client Learning######################################
        if len(round_malicious):
            mal_updates = []
            for kk in np.random.choice(n_attackers, min(n_attackers, args.rand_mal_clients), replace=False):
                mp = copy.deepcopy(FLmodel)
                optimizer = optim.SGD([p for p in mp.parameters() if p.requires_grad], lr=args.lr*(args.lrdc**e), momentum=args.momentum, weight_decay=args.wd)

                scheduler = CosineAnnealingLR(optimizer, T_max=args.local_epochs)
                for epoch in range(args.local_epochs):
                    train_loss, train_acc = train(tr_loaders[kk], mp, criterion, optimizer, args.device)
                    scheduler.step()


                params = []
                for i, (name, param) in enumerate(mp.state_dict().items()):
                    params = param.view(-1).data.type(torch.cuda.FloatTensor) if len(params) == 0 else torch.cat((params, param.view(-1).data.type(torch.cuda.FloatTensor)))

                update =  (params - model_received)

                mal_updates = update[None,:] if len(mal_updates) == 0 else torch.cat((mal_updates, update[None,:]), 0)

                del optimizer, mp, scheduler
                
            mal_agg_update = torch.mean(mal_updates, 0)
            mal_update = our_attack_mkrum(mal_updates, mal_agg_update, len(round_malicious), dev_type='std', threshold=5.0, threshold_diff=1e-5)
            del mal_updates

            for kk in round_malicious:
                user_updates = mal_update[None,:] if len(user_updates) == 0 else torch.cat((user_updates, mal_update[None,:]), 0)
        ########################################Server AGR#########################################
        agg_update, krum_candidate = multi_krum(user_updates, len(round_malicious), multi_k=True)
        del user_updates
        model_received = model_received + agg_update
        FLmodel = getattr(models, args.model)().to(args.device)
        start_idx=0
        state_dict = {}
        previous_name = 'none'
        for i, (name, param) in enumerate(FLmodel.state_dict().items()):
            start_idx = 0 if i == 0 else start_idx + len(FLmodel.state_dict()[previous_name].data.view(-1))
            start_end = start_idx + len(FLmodel.state_dict()[name].data.view(-1))
            params = model_received[start_idx:start_end].reshape(FLmodel.state_dict()[name].data.shape)
            state_dict[name] = params
            previous_name = name

        FLmodel.load_state_dict(state_dict)
        
        if (e+1)%1==0:
            t_loss, t_acc = test(te_loader, FLmodel, criterion, args.device)
            if math.isnan(t_loss) or t_loss > 10000:
                print('val loss %f... exit: The global model is totally destroyed by the adversary' % val_loss)
                break
            if t_acc>t_best_acc:
                t_best_acc=t_acc

            sss='e %d | malicious users: %d | test acc %.4f test loss %.6f best test_acc %.4f' % (e, len(round_malicious), t_acc, t_loss, t_best_acc)
            print (sss)
            with (args.run_base_dir / "output.txt").open("a") as f:
                f.write("\n"+str(sss))
        e+=1