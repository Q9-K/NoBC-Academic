import os
import sys
import json
import time
import gzip
from tqdm import tqdm
from datetime import datetime
from elasticsearch_dsl import connections, Document, Integer, Keyword, Text, Nested, Date, Float, Boolean
from elasticsearch.helpers import parallel_bulk, bulk
from concurrent.futures import ThreadPoolExecutor


cl = connections.create_connection(hosts=['localhost'])


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
            'number_of_shards': 20,
            'number_of_replicas': 0,
            'index.mapping.nested_objects.limit': 500000,
            'index.refresh_interval': '120s',
            'index.translog.durability': 'async',
            'index.translog.flush_threshold_size': '512mb'
        }


def run(file_name):
    with gzip.open(file_name, 'rt', encoding='utf-8') as file:
        i = 0
        data_list = []
        for line in file:
            data = json.loads(line)
            properties_to_extract = ["id", "title", "authorships", "best_oa_location",
                                     "cited_by_count", "concepts", "counts_by_year",
                                     "created_date", "language", "type", "publication_date",
                                     "referenced_works", "related_works"]
            abstract = data.get('abstract_inverted_index')
            data = {key: data[key] for key in properties_to_extract}
            if data.get('id'):
                i += 1
                data['abstract'] = None
                if abstract:
                    positions = [(word, pos) for word, pos_list in abstract.items() for pos in pos_list]
                    positions.sort(key=lambda x: x[1])
                    data['abstract'] = ' '.join([word for word, _ in positions])
                data_list.append({
                    "_op_type": "index",
                    "_index": "work",
                    "_source": data
                })
            if i % 100000 == 0:
                for ok, response in parallel_bulk(client=cl, actions=data_list, chunk_size=5000, queue_size=300, thread_count=8):
                    if not ok:
                        print(response)
                data_list = []
        if len(data_list) > 0:
            i += 1
            for ok, response in parallel_bulk(client=cl, actions=data_list, chunk_size=5000, queue_size=300, thread_count=8):
                if not ok:
                    print(response)


def process_files(folder_path):
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(run, os.path.join(folder_path, file)) for file in files]
        for future in futures:
            future.result()


if __name__ == "__main__":

    WorkDocument.init()

    start_time = datetime.now()
    print("Start insert to ElasticSearch at {}".format(start_time))
    root_path = 'J:/openalex-snapshot/data/works'
    # 获取所有子文件夹
    sub_folders = [f for f in os.listdir(root_path) if os.path.isdir(os.path.join(root_path, f))]

    for sub_folder in tqdm(sub_folders):
        folder_path = os.path.join(root_path, sub_folder)
        process_files(folder_path)
    end_time = datetime.now()
    print("Finished insert to Elasticsearch at{}".format(end_time))
    print("cost time {}".format(end_time-start_time))
