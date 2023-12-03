import os
import sys
import json
import time
import gzip
from tqdm import tqdm
from datetime import datetime
from elasticsearch_dsl import connections, Document, Integer, Keyword, Text, Nested, Date, Float, Boolean
from elasticsearch.helpers import parallel_bulk


class WorkDocument(Document):
    id = Keyword()
    title = Text()
    authorships = Nested(
        properties={
            "author": Nested(
                properties={
                    "id": Keyword(),
                    "display_name": Keyword(),
                    "orcid": Keyword()
                }
            ),
            "author_position": Keyword(),
            "countries": Keyword()
        }
    )
    best_oa_location = Nested(
        properties={
            "is_oa": Boolean(),
            "landing_page_url": Keyword(),
            "pdf_url": Keyword(),
            "source": Nested(
                properties={
                    "id": Keyword(),
                    "display_name": Keyword(),
                    "issn_l": Keyword(),
                    "issn": Keyword(),
                    "host_organization": Keyword(),
                    "type": Keyword(),
                }
            ),
            "license": Keyword(),
            "version": Keyword(),
        })
    cited_by_count = Integer()
    concepts = Nested(
        properties={
            "id": Keyword(),
            "wikidata": Keyword(),
            "display_name": Keyword(),
            "level": Integer(),
            "score": Float()
        }
    )
    counts_by_year = Nested(
        properties={
            "year": Integer(),
            "works_count": Integer(),
            "cited_by_count": Integer(),
        }
    )
    created_date = Date()
    language = Keyword()
    type = Keyword()
    publication_date = Date()
    referenced_works = Keyword(multi=True)
    related_works = Keyword(multi=True)
    abstract = Text()


    class Index:
        name = 'work'
        settings = {
            'number_of_shards': 5,
            'number_of_replicas': 0,
            'index.mapping.nested_objects.limit': 500000
        }

def run(client, file_name):
    with gzip.open(file_name, 'rt', encoding='utf-8') as file:
        i = 0
        data_list = []
        print("start indexing file {}".format(file_name))
        start_time = time.perf_counter()
        for line in file:
            data = json.loads(line)
            properties_to_extract = ["id", "title", "authorships", "best_oa_location",
                                     "cited_by_count", "concepts", "counts_by_year",
                                     "created_date", "language", "type", "publication_date",
                                     "referenced_works", "related_works"]
            abstract = data.get('abstract_inverted_index')
            data = {key: data[key] for key in properties_to_extract}
            if data.get('id') and data.get('title'):
                i += 1
                data['abstract'] = None
                if abstract:
                    positions = [(word, pos) for word, pos_list in abstract.items() for pos in pos_list]
                    positions.sort(key=lambda x: x[1])
                    data['abstract'] = ' '.join([word for word, _ in positions])
                data_list.append({
                    "_op_type": "index",
                    "_index": "work",
                    "_id": data.get('id'),
                    "_source": data
                })
            if i % 5000 == 0:
                start_time1 = time.time()
                for ok, response in parallel_bulk(client=client, actions=data_list, chunk_size=5000):
                    if not ok:
                        print(response)
                data_list = []
                end_time1 = time.time()
                print("circle {} process time = {}s".format(int(i/5000), end_time1-start_time1))
        if data_list:
            start_time1 = time.time()
            i += 1
            for ok, response in parallel_bulk(client=client, actions=data_list, chunk_size=5000):
                if not ok:
                    print(response)
            end_time1 = time.time()
            print("circle {} process time = {}s".format(int(i / 5000), end_time1 - start_time1))
        end_time = time.perf_counter()
        print("finished indexing file {} process time= {} min, end at {}".format(file_name, (end_time-start_time)/60, datetime.now()))


if __name__ == "__main__":
    cl = connections.create_connection(hosts=['localhost'])
    WorkDocument.init()
    # print('日志路径', os.path.join(os.path.dirname(os.path.abspath(__file__)), "WorkImport.log"))
    #
    # with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "WorkImport.log"), 'w', encoding='utf-8') as file:
    print("Start insert to ElasticSearch at {}".format(datetime.now()))
    # original_stdout = sys.stdout
    # sys.stdout = file
    root_path = '/data/openalex-snapshot/data/works'
    # 获取所有子文件夹
    sub_folders = [f for f in os.listdir(root_path) if os.path.isdir(os.path.join(root_path, f))]
    for sub_folder in tqdm(sub_folders):
        folder_path = os.path.join(root_path, sub_folder)
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        for zip_file in files:
            file_name = os.path.join(folder_path, zip_file)
            run(cl, file_name)
        # sys.stdout = original_stdout
    print("Finished insert to Elasticsearch at{}".format(datetime.now()))
