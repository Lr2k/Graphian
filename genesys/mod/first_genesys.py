'''
初めて作る遺伝子系システム。
複数の配列サイズは受け入れ可能だが、変動は想定していない。
交叉、変異も実装する。
交叉は同じ配列サイズを持つ遺伝子間のみで行う。
'''

import random, copy

GENE_SYS_ID = "first_genesys"

class gene():
    '''
    遺伝子。

    Attributes
    ----------
    values: list[float]
        要素は0から1の値を取る。
    meta_values: list[float | int | bool] | None
        変動させない情報を格納する領域。
    score: float
        遺伝子の評価値。
    '''
    gene_sys_id = GENE_SYS_ID
    def __init__(self, size: int, meta_values: list[float | int | bool] | None = None, values:list[float] | None = None, score: float = 0.5):
        '''
        Parameters
        ----------
        size: int
          遺伝情報の要素数
        values: list[float], optional.
          引用する遺伝情報がある場合は指定する。
          指定がない場合は、sizeに合わせ
        meta_values: list[float | int | bool], optional.
          変動しない情報を格納する。
        score: float, default is 0.5.
          遺伝子の評価値。
        '''
        self.score = score
        self.values: list[float]
        if values is None:
            self.values = [random.uniform(0,1) for i in range(size)]
        else:
            if len(values) == size:
                self.values = values
            else:
                raise ValueError(f"sizeとvaluesのサイズが合わない。(size:{size}, values size:{len(values)}")

        self.meta_values = meta_values
    
    def size(self):
        return len(self.values)

class multi_size_gene_pool():
    '''
    複数の遺伝子をまとめて管理し、交叉や変異などの調整を行う。

    Attribute
    ---------
    gene_ls: list[gene]
    gene_by_size: dict[int, list[gene]]
    size: int
        扱う遺伝子の数を規定する。ただし、厳密には管理しない。
    target_system: str or None.
    '''

    gene_sys_id = GENE_SYS_ID
    def __init__(self, size: int | None = None, gene_ls: list[gene] | None = None, target_system: str | None = None):
        '''
        Parameters
        ----------
        size: int, Optional.
            扱う遺伝子の数を規定する。ただし、厳密には管理しない。
        gene_ls: list[gene], Optional.
            利用する。
        target_system: str, Optional.
        '''
        self.gene_ls: list[gene] = list()
        self.genes_by_size: dict[int, list[gene]] = dict()
        if gene_ls:
            self.gene_ls += gene_ls
            for g in gene_ls:
                if g.size() in self.genes_by_size.keys():
                    self.genes_by_size[g.size()].append(g)
                else:
                    self.genes_by_size[g.size()] = [g,]
        
        if size:
            self.size = size
        else:
            self.size = len(self.gene_ls)

        self.target_system = target_system

    def pick_random(self, num: int) -> list[gene]:
        '''
        ランダムに指定した数の遺伝子を取得する。アドレス渡し。

        Parameters
        ----------
        num: int
            取得する数。
        '''
        return random.sample(self.gene_ls, num)
        
    def pick_by_score(self, num: int, reverse: bool = True) -> list[gene]:
        '''
        スコア順で遺伝子を取得する。デフォルトでは高い順に抽出する。
        アドレス渡し。

        Parameters
        ----------
        num: int
            取得する数。
        reverse: bool, default is True.
            Trueの場合、スコアが高い順。
        '''
        sorted_gene_ls = sorted(
            self.gene_ls,
            key=lambda g: g.score,
            reverse=reverse
        )
        return sorted_gene_ls[:num]
    
    def update_score(self, g: gene, result: bool, change_rate: float = 0.1):
        '''
        遺伝子の評価を更新する。

        Parameters
        ----------
        g: gene
        result: bool
            評価する結果の場合はTrue、しない場合はFalseを指定する。
        change_rate: float, default is 0.1.
            変動幅を指定する。
        '''
        if result:
            g.score += (1 - g.score) * change_rate
        else:
            g.score = g.score * (1 - change_rate)
    
    def mix_gene(self, position_range: int = 3, eliminate_rate: float = 0.1):
        '''
        遺伝子を交差させる。
        eliminate_rateでscoreが低いものから数を減らし、
        ランダムに選ばれた2つの遺伝子を交差させ補充する。
        元となる遺伝子は除外されなかった遺伝子から選ばれる。
        交叉点の数はposition_rangeで上限を指定し、ランダムに設定される。

        Parameters
        ----------
        position_range: int, default is 3.
            交差点の数の上限を指定する。
        eliminate_rate: float, default is 0.1.
            置き換える遺伝子の割合。0から1未満で指定する。1
        '''
        for gene_size, gs in self.genes_by_size.items():
            gs_size = len(gs)
            eliminate_num = int(gs_size * eliminate_rate)
            sorted_gs = sorted(gs, key=lambda g: g.score, reverse=True)

            survived_gs = sorted_gs[:gs_size-eliminate_num]
            eliminated_gs = sorted_gs[gs_size-eliminate_num:]

            new_gs: list[gene] = list()
            for i in range(eliminate_num):
                p1_gene, p2_gene = random.sample(survived_gs, 2)
                new_gs.append(gene(
                    size=gene_size,
                    values=mix_arr(
                        p1_gene.values, p2_gene.values,
                        random.randint(1, position_range),
                    ),
                    meta_values=copy.deepcopy(p1_gene.meta_values),
                ))
            
            self.append_genes(new_gs)
            self.eliminate_genes(eliminated_gs)
    
    def mutate_gene(self, target_rate: float = 0.7, change_range: float = 0.05):
        '''
        遺伝子に突然変異を起こす。
        対象はすべての遺伝子となる。
        target_rateでは、遺伝子の要素ごとに変異が起こる確率を決める。

        Parameters
        ----------
        target_rate: float, default is 0.7
            遺伝子の要素ごとに変異が起こる確率。
        change_range: float, default is 0.05
            変異が起こった場合に、遺伝子の要素の値が変動率の幅。
        '''
        for g in self.gene_ls:
            g.values = mutate_arr(g.values, target_rate, change_range)

    def append_genes(self, gene_ls: list[gene], expand_size: bool = False):
        '''
        遺伝子をプールに追加する。

        gene_ls: list[gene]
            プールに追加する遺伝子。
        expand_size: bool, default is False.
            Trueの場合、追加する遺伝子の数だけsizeを大きくする。
            Falseを指定してもsizeを逸脱する遺伝子を排除しない。
        '''
        if expand_size:
            self.size += len(gene_ls)
        
        for g in gene_ls:
            self.gene_ls.append(g)
            
            if g.size() in self.genes_by_size.keys():
                self.genes_by_size[g.size()].append(g)
            else:
                self.genes_by_size[g.size()] = [g,]
    
    def eliminate_genes(self, gene_ls: list[gene], shrink_size: bool = False):
        '''
        遺伝子をプールから排除する。遺伝子のオブジェクト削除は行わない。

        Parameters
        ----------
        gene_ls: list[gene]
            排除する遺伝子。
        shrink_size: bool, default is False.
            Trueの場合、追加する遺伝子の数だけsizeを小さくする。
            Falseを指定しても不足した分の遺伝子を追加しない。
        '''
        if shrink_size:
            self.size -= len(gene_ls)
        
        for g in gene_ls:
            self.gene_ls.remove(g)
            self.genes_by_size[g.size()].remove(g)

def mutate_arr(arr: list[float], target_rate=0.7, change_range=0.05) -> list[float]:
    new_arr: list[float] = list()
    for i, old_v in enumerate(arr):
        if random.random() < target_rate:
            if random.choice([True, False]):
                new_arr.append(old_v + (1-old_v) * random.uniform(0, change_range))
            else:
                new_arr.append(old_v * (1 - random.uniform(0, change_range)))
        else:
            new_arr.append(old_v)
    
    return new_arr

def mix_arr(f_gene_values, s_gene_values, position_num: int) -> list[float]:
    match position_num:
        case 0:
            return f_gene_values
        case _:
            position = random.randint(0,len(f_gene_values)-1)
            return mix_arr(f_gene_values[:position]+s_gene_values[position:], s_gene_values[:position]+f_gene_values[position:], position_num-1)

if __name__ == "__main__":
    pool = multi_size_gene_pool()
    pool.append_genes(
        gene_ls=[
            gene(size=100, meta_values=(1,True, 0.4))
            for _ in range(100)
        ],
        expand_size=True
    )
    print(len(pool.gene_ls))
    gs = pool.pick_by_score(15)
    gs_rev = pool.pick_by_score(15, True)
    for g in gs + gs_rev:
        print(g.score)


    picked_gs_1 = pool.pick_random(10)
    picked_gs_2 = pool.pick_random(10)
    
    for g in picked_gs_1:
        pool.update_score(g, result=True, change_rate=0.1)
    
    for g in picked_gs_2:
        pool.update_score(g, result=False, change_rate=0.1)

    print("=================")
    gs = pool.pick_by_score(15)
    gs_rev = pool.pick_by_score(15, False)
    for g in gs + gs_rev:
        print(g.score)
    
    pool.mix_gene(position_range=5)

    print("=================")
    gs = pool.pick_by_score(15)
    gs_rev = pool.pick_by_score(15, False)
    for g in gs + gs_rev:
        print(g.score)
    
    print(gs[0].values[:10])
    pool.mutate_gene()
    print(gs[0].values[:10])
    
    for i in range(10):
        print(id(pool.pick_random(1)[0]))