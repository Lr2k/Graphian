from genesys.mod import first_genesys

gene_sys_map = {
    "first_genesys": first_genesys,
}

def name_solver(gene_sys_name: str):
    match gene_sys_name:
        case "first_genesys":
            return first_genesys.gene, first_genesys.multi_size_gene_pool
        case _:
            raise ValueError("{gene_sys_name}に当たる遺伝子系システムがありません。")