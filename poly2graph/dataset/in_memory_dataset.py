import numpy as np
import networkx as nx
import torch
from torch_geometric.data import Data, InMemoryDataset
from torch_geometric.utils import from_networkx
from ..line_graph import LG_undirected
from .post import hash_labels
from .sampling_1band import load_dataset
from gdown import download_folder

class Dataset_nHSG(InMemoryDataset):
    def __init__(self, root, is_G=True,
                 transform=None, pre_transform=None, pre_filter=None):
        super().__init__(root, transform, pre_transform, pre_filter)

        self.is_G = is_G
        if is_G:
            self.load(self.processed_paths[0])
        else:
            self.load(self.processed_paths[1])

    @property
    def raw_file_names(self):
        return ['dataset_graph_dim6.h5']

    @property
    def processed_file_names(self):
        return ['data_G.pt', 'data_L.pt']
    
    def download(self, gdown_kwargs={'resume': True}):
        # folder_prefix = 'https://drive.google.com/drive/folders/'
        # raw_id = '1S6MsMkEkiZg5ZfVzULROj8mQtLPFXySR?usp=sharing'
        # processed_id = '1_DWajzz2P0AKNMrNG9GKabjtJwLM6wrk?usp=sharing'
        # download_folder(id=raw_id, output=self.root, resume=True, **gdown_kwargs)
        # download_folder(id=processed_id, output=self.root, resume=True, **gdown_kwargs)
        root_id = '12wdPCdDya6tpeJy7cjpbhnv-tNz3f21K?usp=sharing'
        download_folder(id=root_id, output=self.root, **gdown_kwargs)

    def process(self):
        nx_Gs, labels = load_dataset(self.raw_paths[0][:-3]) # strip ".h5" extension
        labels_signs = np.where(np.abs(labels) < 1e-6, 0, 1)
        hashed_labels = hash_labels(labels_signs, 2)
        G_list = []; L_list = []
        for i, nx_G in enumerate(nx_Gs):
            print(f'Processing graph {i+1}/{len(nx_Gs)}')
            nx_G = self._preprocess_nx_G(nx_G)
            nx_L = self._to_nx_L(nx_G)
            pyg_G = from_networkx(nx_G, group_node_attrs=['o'], group_edge_attrs=['weight', 'pts5'])
            pyg_L = from_networkx(nx_L, group_node_attrs=['weight', 'pts5'], group_edge_attrs=['triplet_center', 'angle'])
            # add graph-level attributes to pyg_G
            G_list.append(Data(x=pyg_G.x,
                               pos=pyg_G.pos,
                               edge_index=pyg_G.edge_index,
                               edge_attr=pyg_G.edge_attr,
                               y=torch.tensor([hashed_labels[i]], dtype=torch.long),
                               y_multi=torch.tensor([labels_signs[i]], dtype=torch.long),
                               free_coeffs=torch.tensor([labels[i]], dtype=torch.float32),
                               full_coeffs=pyg_G.polynomial_coeff,
                               Emax=pyg_G.Emax))
            L_list.append(Data(x=pyg_L.x,
                               pos=pyg_L.pos,
                               edge_index=pyg_L.edge_index,
                               edge_attr=pyg_L.edge_attr))
        self.save(G_list, self.processed_paths[0])
        self.save(L_list, self.processed_paths[1])
    
    @staticmethod
    def _preprocess_nx_G(Phi_graph: nx.MultiGraph) -> nx.MultiGraph:

        Phi_graph = Phi_graph.copy()

        for n in Phi_graph.nodes(data=True):
            # delete 'pts' attribute to save memory
            if 'pts' in n[1]: del n[1]['pts']
            # scale the node positions back to actual energy values
            n[1]['pos'] = n[1]['o']/128

        for e in Phi_graph.edges(data=True):
            # sample `pts5` as G's edge feature
            pts5_idx = np.round(np.linspace(0, len(e[2]['pts'])-1, 7)).astype(int)[1:-1]
            e[2]['pts5'] = e[2]['pts'][pts5_idx].flatten()
            # sample `pts2` for augmenting L's edge feature `angle`
            pts2_idx = np.round(np.linspace(0, len(e[2]['pts'])-1, 4)).astype(int)[1:-1]
            e[2]['pts2'] = e[2]['pts'][pts2_idx]
            # delete 'pts' attribute to save memory
            if 'pts' in e[2]: del e[2]['pts']

        return Phi_graph
    
    @staticmethod
    def _to_nx_L(Phi_graph: nx.MultiGraph) -> nx.MultiGraph:
        L = LG_undirected(Phi_graph, triplet_feature=True)
        if L.number_of_edges() == 0:
            L = LG_undirected(Phi_graph, selfloops=True, triplet_feature=True)

        # choose the middle point of the edge as the node position for L
        for n in L.nodes(data=True):
            n[1]['pos'] = n[1]['pts5'][4:6]/128
            if 'pts2' in n[1]: del n[1]['pts2']
        
        return L
    
class Dataset_nHSG_Paired(torch.utils.data.Dataset):
    def __init__(self, root, 
                 graphs=None, line_graphs=None,
                 transform=None, pre_transform=None, pre_filter=None):
        
        self.root = root

        if graphs is not None:
            self.graphs = graphs
        else:
            self.graphs = Dataset_nHSG(root, is_G=True, 
                                 transform=transform, pre_transform=pre_transform, pre_filter=pre_filter)

        if line_graphs is not None:
            self.line_graphs = line_graphs
        else:
            self.line_graphs = Dataset_nHSG(root, is_G=False, 
                                 transform=transform, pre_transform=pre_transform, pre_filter=pre_filter)

        assert len(self.graphs) == len(self.line_graphs), "Graphs and line graphs must have the same length"


    def __len__(self):
        return len(self.graphs)


    def __getitem__(self, idx):
        return self.graphs[idx], self.line_graphs[idx]