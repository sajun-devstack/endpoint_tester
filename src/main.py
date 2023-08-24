from typing import List
from fastapi import FastAPI, HTTPException
import json
import requests
from enum import Enum
import kubernetes as k8s
from kubernetes.client.api_client import ApiClient
from kubernetes.client.exceptions import ApiException
import os

k8s.config.load_incluster_config()
k8s_host = ApiClient().configuration.host
default_token = ''.join(open('/var/run/secrets/kubernetes.io/serviceaccount/token', 'r').readlines())
namespace = ''.join(open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', 'r').readlines())

app = FastAPI()

with open('data/k8s_endpoints.json', 'r') as f:
    k8s_endpoints = json.loads('\n'.join(f.readlines()))
K8sEndpointName = Enum('K8sEndpointName', {k:k for k in k8s_endpoints.keys()})

with open('data/ks_endpoints.json', 'r') as f:
    ks_endpoints = json.loads('\n'.join(f.readlines()))
KSEndpointName = Enum('KSpointName', {k:k for k in ks_endpoints.keys()})

class RequesterType(Enum):
    serviceaccount = 'serviceaccount'
    user = 'user'

def _create_serviceaccount(name, roles, clusterroles):
    # create serviceaccount
    metadata = k8s.client.V1ObjectMeta(name=name)
    sa = k8s.client.V1ServiceAccount(metadata=metadata)
    k8s.client.CoreV1Api().create_namespaced_service_account(namespace, sa)

    # create rolebindings
    for r in roles:
        metadata = k8s.client.V1ObjectMeta(name=f"{r}-{name}", labels={"owner": name})
        role_ref = k8s.client.V1RoleRef(api_group='rbac.authorization.k8s.io', kind='Role', name=r)
        subject = k8s.client.V1Subject(kind='ServiceAccount', name=name, namespace=namespace)
        rb = k8s.client.V1RoleBinding(metadata=metadata, role_ref=role_ref, subjects=[subject])
        k8s.client.RbacAuthorizationV1Api().create_namespaced_role_binding(namespace, rb)

    # create clusterrolebindings
    for r in clusterroles:
        metadata = k8s.client.V1ObjectMeta(name=f"{r}-{name}", labels={"owner": name})
        role_ref = k8s.client.V1RoleRef(api_group='rbac.authorization.k8s.io', kind='ClusterRole', name=r)
        subject = k8s.client.V1Subject(kind='ServiceAccount', name=name, namespace=namespace)
        rb = k8s.client.V1ClusterRoleBinding(metadata=metadata, role_ref=role_ref, subjects=[subject])
        k8s.client.RbacAuthorizationV1Api().create_cluster_role_binding(rb)

def _delete_serviceaccount(name):
    # remove associated rolebindings
    k8s.client.RbacAuthorizationV1Api().delete_collection_namespaced_role_binding(namespace,label_selector=f"owner={name}")
    k8s.client.RbacAuthorizationV1Api().delete_collection_cluster_role_binding(label_selector=f"owner={name}")

    # delete serviceaccount
    k8s.client.CoreV1Api().delete_namespaced_service_account(name, namespace)

def _receive_token_from_sa(name):
    spec = k8s.client.V1TokenRequestSpec(audiences=[])
    tokenrequest = k8s.client.AuthenticationV1TokenRequest(spec=spec)
    res = k8s.client.CoreV1Api().create_namespaced_service_account_token(name, namespace, tokenrequest)

    token = res.status.token

    return token

def _request(method, url, serviceaccount):
    try:
        token = _receive_token_from_sa(serviceaccount)
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=f"Cannot receive a token for the serviceaccount '{serviceaccount}': {e.reason}")
    
    try:
        response = requests.request(method, url, headers={"Authorization": f"bearer {token}"})
    except e:
        raise HTTPException(status_code=e.status_code, detail=e.reason)

    if "text" in response.headers["Content-Type"]:
        response_body = response.text
    elif "json" in response.headers["Content-Type"]:
        response_body = response.json()

    return response_body


@app.post("/kubernetes/{endpoint_name}")
def request_k8s(endpoint_name: K8sEndpointName, serviceaccount:str = 'tester', namespace: str = '', name: str = ''):
    method, endpoint = k8s_endpoints[endpoint_name.value]
    url = k8s_host + endpoint
    url = url.format(namespace=namespace, name=name)

    return _request(method, url, serviceaccount)


@app.post("/kubesphere/{endpoint_name}")
def request_kubesphere(endpoint_name: KSEndpointName, serviceaccount:str = 'tester', cluster: str = '', namespace: str = '', name: str = ''):
    method, endpoint = ks_endpoints[endpoint_name.value]
    url = k8s_host + endpoint
    url = url.format(cluster=cluster, namespace=namespace, name=name)

    return _request(method, url, serviceaccount)


@app.post("/serviceaccount/{serviceaccount}")
def create_new_serviceaccount(serviceaccount: str, roles: List[str] = [], clusterroles: List[str] = []):
    try:
        return _create_serviceaccount(serviceaccount, roles, clusterroles)
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.reason)


@app.delete("/serviceaccount/{serviceaccount}")
def delete_serviceaccount(serviceaccount: str):
    try:
        return _delete_serviceaccount(serviceaccount)
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.reason)