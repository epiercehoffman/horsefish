import os
import subprocess
import ast
import shutil
import argparse
from firecloud import api as fapi

def call_fiss(fapifunc, okcode, *args, specialcodes=None, **kwargs):
    ''' call FISS (firecloud api), check for errors, return json response

    function inputs:
        fapifunc : fiss api function to call, e.g. `fapi.get_workspace`
        okcode : fiss api response code indicating a successful run
        specialcodes : optional - LIST of response code(s) for which you don't want to retry
        *args : args to input to api call
        **kwargs : kwargs to input to api call

    function returns:
        response.json() : json response of the api call if successful
        OR
        response : non-parsed API response if you submitted specialcodes

    example use:
        output = call_fiss(fapi.get_workspace, 200, 'help-gatk', 'Sequence-Format-Conversion')
    '''
    # call the api 
    response = fapifunc(*args, **kwargs) 
    # print(response.status_code)

    # check for errors; this is copied from _check_response_code in fiss
    if type(okcode) == int:
        # codes = [okcode]
        if specialcodes is None:
            codes = [okcode]
        else:
            codes = [okcode]+specialcodes
    if response.status_code not in codes:
        print(response.content)
        raise ferrors.FireCloudServerError(response.status_code, response.content)
    elif specialcodes is not None:
        return response

    # return the json response if all goes well
    return response.json()


def update_notebooks(workspace_name, workspace_project, replace_this, with_this):
    print("Updating NOTEBOOKS for " + workspace_name)

    ## update notebooks
    # Getting the workspace bucket
    r = fapi.get_workspace(workspace_project, workspace_name)
    fapi._check_response_code(r, 200)
    workspace = r.json()
    bucket = workspace['workspace']['bucketName']

    # check if bucket is empty
    gsutil_args = ['gsutil', 'ls', 'gs://' + bucket + '/']
    bucket_files = subprocess.check_output(gsutil_args)
    # Check output produces a string in Py2, Bytes in Py3, so decode if necessary
    if type(bucket_files) == bytes:
        bucket_files = bucket_files.decode().split('\n')
    # print(bucket_files)

    editingFolder = "../notebookEditingFolder"

    # if the bucket isn't empty, check for notebook files and copy them
    if 'gs://'+bucket+'/notebooks/' in bucket_files: #len(bucket_files)>0:
        # bucket_prefix = 'gs://' + bucket
        # Creating the Notebook Editing Folder
        if os.path.exists(editingFolder):
            shutil.rmtree(editingFolder)
        os.mkdir(editingFolder)
        # Runing a gsutil ls to list files present in the bucket
        gsutil_args = ['gsutil', 'ls', 'gs://' + bucket + '/notebooks/**']
        bucket_files = subprocess.check_output(gsutil_args, stderr=subprocess.PIPE)
        # Check output produces a string in Py2, Bytes in Py3, so decode if necessary
        if type(bucket_files) == bytes:
            bucket_files = bucket_files.decode().split('\n')
        #Getting all notebook files
        notebook_files = []
        print("Copying files to local disk...")
        for bf in bucket_files:
            if ".ipynb" in bf:
                notebook_files.append(bf)
                # Downloading notebook to Notebook Editing Folder
                gsutil_args = ['gsutil', 'cp', bf, editingFolder]
                print('  copying '+bf)
                copyFiles = subprocess.check_output(gsutil_args, stderr=subprocess.PIPE)
        #Does URL replacement
        print("Replacing text in files...")
        sed_command = "sed -i '' -e 's#{replace_this}#{with_this}#' {editing_folder}/*.ipynb".format(
                                        replace_this=replace_this,
                                        with_this=with_this,
                                        editing_folder=editingFolder)
        os.system(sed_command)
        #Upload notebooks back into workspace
        print("Uploading files to bucket...")
        for filename in os.listdir(editingFolder):
            if not filename.startswith('.'):
                if not filename.endswith(".ipynb"):
                    print("  WARNING: non notebook file, not replacing "+filename)
                else:
                    print('  uploading '+filename)
                    gsutil_args = ['gsutil', 'cp', editingFolder+'/'+filename,  'gs://' + bucket+"/notebooks/"+filename]
                    uploadfiles = subprocess.check_output(gsutil_args, stderr=subprocess.PIPE)
                    #Remove notebook from the Notebook Editing Folder
                    os.remove(editingFolder+'/'+filename)
        #Deleting Notebook Editing Folder to delete any old files lingering in the folder
        shutil.rmtree(editingFolder)
    else:
        print("Workspace has no notebooks folder")


def find_and_replace(attr, value, replace_this, with_this):

    updated_attr = None
    if isinstance(value, str): # if value is just a string
        if replace_this in value:
            new_value = value.replace(replace_this, with_this)
            updated_attr = fapi._attr_set(attr, new_value)
    elif isinstance(value, dict):
        if replace_this in str(value):
            value_str = str(value)
            value_str_new = value_str.replace(replace_this, with_this)
            value_new = ast.literal_eval(value_str_new)
            updated_attr = fapi._attr_set(attr, value_new)
    elif isinstance(value, bool):
        pass
    elif value is None:
        pass
    else: # some other type, hopefully this doesn't exist
        if replace_this in value:
            print('unknown type of attribute')
            print('attr: '+attr)
            print('value: '+value)

    return updated_attr


def update_attributes(workspace_name, workspace_project, replace_this, with_this):
    ## update workspace data attributes
    print("Updating ATTRIBUTES for " + workspace_name)

    # get data attributes
    response = call_fiss(fapi.get_workspace, 200, workspace_project, workspace_name)
    attributes = response['workspace']['attributes']

    attrs_list = []
    for attr in attributes.keys():
        value = attributes[attr]
        updated_attr = find_and_replace(attr, value, replace_this, with_this)
        if updated_attr:
            attrs_list.append(updated_attr)

    if len(attrs_list) > 0:
        response = fapi.update_workspace_attributes(workspace_project, workspace_name, attrs_list)
        if response.status_code == 200:
            print('Updated attributes:')
            for attr in attrs_list:
                print(attr)


def update_entities(workspace_name, workspace_project, replace_this, with_this):
    ## update workspace entities
    print("Updating DATA ENTITIES for " + workspace_name)

    # get data attributes
    response = call_fiss(fapi.get_entities_with_type, 200, workspace_project, workspace_name)
    entities = response

    for ent in entities:
        ent_name = ent['name']
        ent_type = ent['entityType']
        ent_attrs = ent['attributes']
        attrs_list = []
        for attr in ent_attrs.keys():
            value = ent_attrs[attr]
            updated_attr = find_and_replace(attr, value, replace_this, with_this)
            if updated_attr:
                attrs_list.append(updated_attr)

        if len(attrs_list) > 0:
            response = fapi.update_entity(workspace_project, workspace_name, ent_type, ent_name, attrs_list)
            if response.status_code == 200:
                print('Updated entities:')
                for attr in attrs_list:
                    print('   '+attr['attributeName']+' : '+attr['addUpdateAttribute'])


def is_in_bucket_list(path):
    bucket_list = ['fc-122c390c-f0b9-4b01-82ae-3e87e858e01a',
        'fc-12be498d-4812-489b-9b02-023db71a470f',
        'fc-37557664-acea-408f-a944-027ed65502e5',
        'fc-38aeaeaf-02c4-493d-a35b-a4f95f2c2fae',
        'fc-3d22b428-2d11-483e-9d6e-7b13c3546e27',
        'fc-3e3e2d8c-ff7c-4a5d-a0c4-1b2d8a96cf4b',
        'fc-4ccb3566-f985-4e68-993c-ec666287c45b',
        'fc-52fb4dc7-0957-49c6-9851-95951ea5308e',
        'fc-67ecfd09-da44-465d-8e09-fdf082fc1f8d',
        'fc-6cff0a0e-16db-47bd-b482-91618628e87d',
        'fc-75bd7886-4635-4453-83af-76951e9c0f4b',
        'fc-7e333c4f-dcbf-4c0d-8644-07a1bccde045',
        'fc-8261513a-5f0c-4be0-ae42-62bcf00dfc52',
        'fc-9bc3b4e4-f2a1-4ef3-b408-cf74f1916610',
        'fc-a78c8a3c-890b-4953-a67d-f226685ead99',
        'fc-a9d8dab3-1c57-4e9e-879a-f9d39441bfb5',
        'fc-ab3e3ef8-5e90-47c1-8f44-246552248074',
        'fc-be4e0e22-021e-4edc-a52e-56d9f053119d',
        'fc-c0f9b627-a631-4f6c-bbfe-5edbe80d7eff',
        'fc-cd11a278-cda3-4211-9ea4-c964c78e9bb6',
        'fc-dd9c4e05-3511-4d3e-bc23-92815d14ffa1',
        'fc-ddea25e3-a077-4f5f-a9d1-9661431186b2',
        'fc-e02d3247-5469-4a5c-8b66-c4397eeff5d0',
        'fc-e67c6510-d7f1-4bc3-b55e-2dfad7d56786',
        'fc-e6c84ae9-9ac9-4b35-ae86-ac9f04824bf8',
        'fc-e9440d64-3fad-44bc-a2c7-c439a94aff29',
        'fc-ed48dede-1e5e-41ff-b3a1-0ef4f9797cd4',
        'fc-effb3f55-962a-4b1f-b41d-63234d7e5735',
        'fc-fd538f2b-e8bf-478a-8620-2c4c13a3e664']

    for bucket in bucket_list:
        if bucket in path:
            return True
    return False


def is_gs_path(attr, value, str_match='gs://'):

    if isinstance(value, str): # if value is just a string
        if str_match in value:
            return True
    elif isinstance(value, dict):
        if str_match in str(value):
            return True
    elif isinstance(value, bool):
        pass
    elif value is None:
        pass
    else: # some other type, hopefully this doesn't exist
        if str_match in value:
            print('unknown type of attribute')
            print('attr: '+attr)
            print('value: '+value)

    return False

def update_entity_data_paths(workspace_name, workspace_project):
    print("Listing all gs:// paths in DATA ENTITIES for " + workspace_name)

    # get data attributes
    response = call_fiss(fapi.get_entities_with_type, 200, workspace_project, workspace_name)
    entities = response
    
    paths_without_replacements = {} # where we store paths for which we don't have a replacement

    replacements_made = 0
    
    for ent in entities:
        ent_name = ent['name']
        ent_type = ent['entityType']
        ent_attrs = ent['attributes']
        gs_paths = {}
        attrs_list = []
        for attr in ent_attrs.keys():
            if is_gs_path(attr, ent_attrs[attr]): # this is a gs:// path
                original_path = ent_attrs[attr]
                if is_in_bucket_list(original_path): # this is a path we think we want to update
                    new_path = get_replacement_path(original_path)
                    gs_paths[attr] = original_path
                    if new_path:
                        # format the update
                        updated_attr = fapi._attr_set(attr, new_path)
                        attrs_list.append(updated_attr) # what we have replacements for
                        replacements_made += 1
                    else:
                        paths_without_replacements[attr] = original_path # what we don't have replacements for
        
        if len(gs_paths) > 0:
            print(f'Found the following paths to update in {ent_name}:')
            for item in gs_paths.keys():
                print('   '+item+' : '+gs_paths[item])
        
        if len(attrs_list) > 0:
            response = fapi.update_entity(workspace_project, workspace_name, ent_type, ent_name, attrs_list)
            if response.status_code == 200:
                print(f'\nUpdated entities in {ent_name}:')
                for attr in attrs_list:
                    print('   '+attr['attributeName']+' : '+attr['addUpdateAttribute'])

    if replacements_made == 0:
        print('\nNo paths were updated!')
        
    if len(paths_without_replacements) > 0:
        print('\nWe could not find replacements for the following paths: ')
        for item in paths_without_replacements.keys():
            print('   '+item+' : '+paths_without_replacements[item])
            

def get_replacement_path(original_path):
    ''' input original path; 
    get back either a new destination path or None
    
    TODO: insert Steve's function here
    '''
    if 'fastq' in original_path:
        return original_path
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--workspace_name', help='name of workspace in which to make changes')
    parser.add_argument('--workspace_project', help='billing project (namespace) of workspace in which to make changes')
    parser.add_argument('--replace_this', default=None, help='target string to be replaced')
    parser.add_argument('--with_this', default=None, help='replacement string for every instance of target string ("replace_this")')

    args = parser.parse_args()

    # update the workspace attributes
    if args.replace_this:
        update_attributes(args.workspace_name, args.workspace_project, args.replace_this, args.with_this)
        # update_notebooks(args.workspace_name, args.workspace_project, args.replace_this, args.with_this)
        update_entities(args.workspace_name, args.workspace_project, args.replace_this, args.with_this)
    else:
        list_entity_data_paths(args.workspace_name, args.workspace_project, ['gs://terra-featured-workspaces/'])

