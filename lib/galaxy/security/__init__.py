"""
Galaxy Security

"""
import logging
from galaxy.util.bunch import Bunch
from galaxy.model.orm import *

log = logging.getLogger(__name__)

class Action( object ):
    def __init__( self, action, description, model ):
        self.action = action
        self.description = description
        self.model = model

class RBACAgent:
    """Class that handles galaxy security"""
    permitted_actions = Bunch(
        DATASET_EDIT_METADATA = Action(
            "edit metadata", "Role members can edit this dataset's metadata in the library", "grant" ),
        DATASET_MANAGE_PERMISSIONS = Action(
            "manage permissions", "Role members can manage the roles associated with this dataset", "grant" ),
        DATASET_ACCESS = Action(
            "access", "Role members can import this dataset into their history for analysis", "restrict" )
    )
    def get_action( self, name, default=None ):
        """
        Get a permitted action by its dict key or action name
        """
        for k, v in self.permitted_actions.items():
            if k == name or v.action == name:
                return v
        return default
    def get_actions( self ):
        """
        Get all permitted actions as a list
        """
        return self.permitted_actions.__dict__.values()
    def allow_action( self, user, action, **kwd ):
        raise 'No valid method of checking action (%s) on %s for user %s.' % ( action, kwd, user )
    def guess_derived_permissions_for_datasets( self, datasets = [] ):
        raise "Unimplemented Method"
    def associate_components( self, **kwd ):
        raise 'No valid method of associating provided components: %s' % kwd
    def create_private_user_role( self, user ):
        raise "Unimplemented Method"
    def get_private_user_role( self, user ):
        raise "Unimplemented Method"
    def user_set_default_permissions( self, user, permissions={}, history=False, dataset=False ):
        raise "Unimplemented Method"
    def history_set_default_permissions( self, history, permissions=None, dataset=False, bypass_manage_permission=False ):
        raise "Unimplemented Method"
    def set_dataset_permissions( self, dataset, permissions ):
        raise "Unimplemented Method"
    def get_component_associations( self, **kwd ):
        raise "Unimplemented Method"
    def components_are_associated( self, **kwd ):
        return bool( self.get_component_associations( **kwd ) )
    def convert_permitted_action_strings( self, permitted_action_strings ):
        """
        When getting permitted actions from an untrusted source like a
        form, ensure that they match our actual permitted actions.
        """
        return filter( lambda x: x is not None, [ self.permitted_actions.get( action_string ) for action_string in permitted_action_strings ] )

class GalaxyRBACAgent( RBACAgent ):
    def __init__( self, model, permitted_actions=None ):
        self.model = model
        if permitted_actions:
            self.permitted_actions = permitted_actions
    def allow_action( self, user, action, **kwd ):
        if 'dataset' in kwd:
            return self.allow_dataset_action( user, action, kwd['dataset'] )
        raise 'No valid method of checking action (%s) on %s for user %s.' % ( action, kwd, user )
    def allow_dataset_action( self, user, action, dataset ):
        """Returns true when user has permission to perform an action"""
        if not isinstance( dataset, self.model.Dataset ):
            dataset = dataset.dataset
        if not user:
            if action == self.permitted_actions.DATASET_ACCESS and action.action not in [ adra.action for adra in dataset.actions ]:
                return True # anons only get access, and only if there are no roles required for the access action
            # other actions (or if the dataset has roles defined for the access action) fall through to the false below
        elif action.action not in [ adra.action for adra in dataset.actions ]:
            if action.model == 'restrict':
                return True # implicit access to restrict-style actions if the dataset does not have the action
            # grant-style actions fall through to the false below
        else:
            user_role_ids = sorted( [ r.id for r in user.all_roles() ] )
            perms = self.get_dataset_permissions( dataset )
            if action in perms.keys():
		# the filter() returns a list of the dataset's role ids
		# of which the user is not a member.  so an empty list
		# means the user has all of the required roles.
                if not filter( lambda x: x not in user_role_ids, [ r.id for r in perms[ action ] ] ):
                    return True # user has all of the roles required to perform the action
                # fall through to the false.  user is missing at least one required role
        return False # default is to reject
    def guess_derived_permissions_for_datasets( self, datasets=[] ):
        """Returns a dict of { action : [ role, role, ... ] } for the output dataset based upon provided datasets"""
        perms = {}
        for dataset in datasets:
            if not isinstance( dataset, self.model.Dataset ):
                dataset = dataset.dataset
            these_perms = {}
            # initialize blank perms
            for action in self.get_actions():
                these_perms[ action ] = []
            # collect this dataset's perms
            these_perms = self.get_dataset_permissions( dataset )
            # join or intersect this dataset's permissions with others
            for action, roles in these_perms.items():
                if action not in perms.keys():
                    perms[ action ] = roles
                else:
                    if action.model == 'grant':
                        # intersect existing roles with new roles
                        perms[ action ] = filter( lambda x: x in perms[ action ], roles )
                    elif action.model == 'restrict':
                        # join existing roles with new roles
                        perms[ action ].extend( filter( lambda x: x not in perms[ action ], roles ) )
        return perms
    def associate_components( self, **kwd ):
        if 'user' in kwd:
            if 'group' in kwd:
                return self.associate_user_group( kwd['user'], kwd['group'] )
            elif 'role' in kwd:
                return self.associate_user_role( kwd['user'], kwd['role'] )
        elif 'role' in kwd:
            if 'group' in kwd:
                return self.associate_group_role( kwd['group'], kwd['role'] )
        if 'action' in kwd:
            if 'dataset' in kwd and 'role' in kwd:
                return self.associate_action_dataset_role( kwd['action'], kwd['dataset'], kwd['role'] )
        raise 'No valid method of associating provided components: %s' % kwd
    def associate_user_group( self, user, group ):
        assoc = self.model.UserGroupAssociation( user, group )
        assoc.flush()
        return assoc
    def associate_user_role( self, user, role ):
        assoc = self.model.UserRoleAssociation( user, role )
        assoc.flush()
        return assoc
    def associate_group_role( self, group, role ):
        assoc = self.model.GroupRoleAssociation( group, role )
        assoc.flush()
        return assoc
    def associate_action_dataset_role( self, action, dataset, role ):
        assoc = self.model.ActionDatasetRoleAssociation( action, dataset, role )
        assoc.flush()
        return assoc
    def create_private_user_role( self, user ):
        # Create private role
        role = self.model.Role( name=user.email, description='Private Role for ' + user.email, type=self.model.Role.types.PRIVATE )
        role.flush()
        # Add user to role
        self.associate_components( role=role, user=user )
        return role
    def get_private_user_role( self, user, auto_create=False ):
        role = self.model.Role.filter( and_( self.model.Role.table.c.name == user.email, 
                                             self.model.Role.table.c.type == self.model.Role.types.PRIVATE ) ).first()
        if not role:
            if auto_create:
                return self.create_private_user_role( user )
            else:
                return None
        return role
    def user_set_default_permissions( self, user, permissions = {}, history=False, dataset=False ):
        if user is None:
            return None
        if not permissions:
            permissions = { self.permitted_actions.DATASET_MANAGE_PERMISSIONS : [ self.get_private_user_role( user, auto_create=True ) ] }
        # Delete all of the previous defaults
        for dup in user.default_permissions:
            dup.delete()
            dup.flush()
        # Add the new defaults (if any)
        for action, roles in permissions.items():
            if isinstance( action, Action ):
                action = action.action
            for role in roles:
                dup = self.model.DefaultUserPermissions( user, action, role )
                dup.flush()
        if history:
            for history in user.active_histories:
                self.history_set_default_permissions( history, permissions=permissions, dataset=dataset )
    def user_get_default_permissions( self, user ):
        perms = {}
        for action in self.get_actions():
            perms[ action ] = []
        for dup in user.default_permissions:
            perms[ self.get_action( dup.action ) ].append( dup.role )
        return perms
    def history_set_default_permissions( self, history, permissions={}, dataset=False, bypass_manage_permission=False ):
        if not history.user:
            return None # default permissions on a userless history are none
        if not permissions:
            permissions = self.user_get_default_permissions( history.user )
        for dhp in history.default_permissions:
            dhp.delete()
            dhp.flush()
        for action, roles in permissions.items():
            if isinstance( action, Action ):
                action = action.action
            for role in roles:
                dhp = self.model.DefaultHistoryPermissions( history, action, role )
                dhp.flush()
        if dataset:
            for hda_in_history in history.datasets:
                if len( hda_in_history.dataset.library_associations ):
                    continue # dataset has a library association, don't change the permissions
                if len( [ hda for hda in hda_in_history.dataset.history_associations if hda.history not in history.user.histories ] ):
                    continue # dataset has a history association in a history the user doesn't own, don't change the permissions
                # bypass is used to change permissions of datasets in a userless history when logging in
                if bypass_manage_permission or self.allow_action( history.user, self.permitted_actions.DATASET_MANAGE_PERMISSIONS, dataset=hda_in_history.dataset ):
                    self.set_dataset_permissions( hda_in_history.dataset, permissions )
    def history_get_default_permissions( self, history ):
        perms = {}
        for action in self.get_actions():
            perms[ action ] = []
        for dhp in history.default_permissions:
            perms[ self.get_action( dhp.action ) ].append( dhp.role )
        return perms
    def set_dataset_permissions( self, dataset, permissions={} ):
	# to delete permission on an action, pass in a blank list of
	# roles with that action.  leaving an action out of the perm
	# dict simply leaves those perms untouched (if they exist)
        incoming_actions = []
        for action in permissions.keys():
            if isinstance( action, Action ):
                action = action.action
            incoming_actions.append( action )
        for adra in dataset.actions:
            if adra.action in incoming_actions:
                adra.delete()
                adra.flush()
        for action, roles in permissions.items():
            if isinstance( action, Action ):
                action = action.action
            for role in roles:
                self.associate_components( action=action, dataset=dataset, role=role )
    def get_dataset_permissions( self, dataset ):
        if not isinstance( dataset, self.model.Dataset ):
            dataset = dataset.dataset
        perms = {}
        for action in self.model.Dataset.permitted_actions.__dict__.values():
            perms[ action ] = []
        for adra in dataset.actions:
            perms[ self.get_action( adra.action ) ].append( adra.role )
        return perms
    def copy_dataset_permissions( self, src, dst ):
        if not isinstance( src, self.model.Dataset ):
            src = src.dataset
        if not isinstance( dst, self.model.Dataset ):
            dst = dst.dataset
        self.set_dataset_permissions( dst, self.get_dataset_permissions( src ) )
    def privately_share_dataset( self, dataset, users = [] ):
        intersect = None
        for user in users:
            roles = [ ura.role for ura in user.roles if ura.role.type == self.model.Role.types.SHARING ]
            if intersect is None:
                intersect = roles
            else:
                new_intersect = []
                for role in roles:
                    if role in intersect:
                        new_intersect.append( role )
                intersect = new_intersect
        sharing_role = None
        if intersect:
            for role in intersect:
                if not filter( lambda x: x not in users, [ ura.user for ura in role.users ] ):
                    # only use a role if it contains ONLY the users we're sharing with
                    sharing_role = role
                    break
        if sharing_role is None:
            sharing_role = self.model.Role( name = "Sharing role for: " + ", ".join( [ u.email for u in users ] ),
                                            type = self.model.Role.types.SHARING )
            sharing_role.flush()
            for user in users:
                self.associate_components( user=user, role=sharing_role )
        self.set_dataset_permissions( dataset, { self.permitted_actions.DATASET_ACCESS : [ sharing_role ] } )
    def set_entity_role_associations( self, roles=[], users=[], groups=[], delete_existing_assocs=True ):
        for role in roles:
            if delete_existing_assocs:
                for a in role.users + role.groups:
                    a.delete()
                    a.flush()
            for user in users:
                self.associate_components( user=user, role=role )
            for group in groups:
                self.associate_components( group=group, role=role )
    def get_component_associations( self, **kwd ):
        assert len( kwd ) == 2, 'You must specify exactly 2 Galaxy security components to check for associations.'
        if 'dataset' in kwd:
            if 'action' in kwd:
                return self.model.ActionDatasetRoleAssociation.filter_by( action = kwd['action'].action, dataset_id = kwd['dataset'].id ).first()
        elif 'user' in kwd:
            if 'group' in kwd:
                return self.model.UserGroupAssociation.filter_by( group_id = kwd['group'].id, user_id = kwd['user'].id ).first()
            elif 'role' in kwd:
                return self.model.UserRoleAssociation.filter_by( role_id = kwd['role'].id, user_id = kwd['user'].id ).first()
        elif 'group' in kwd:
            if 'role' in kwd:
                return self.model.GroupRoleAssociation.filter_by( role_id = kwd['role'].id, group_id = kwd['group'].id ).first()
        raise 'No valid method of associating provided components: %s' % kwd
    def check_folder_contents( self, user, entry ):
        """
    	Return true if there are any datasets under 'folder' that the
    	user has access permission on.  We do this a lot and it's a
    	pretty inefficient method, optimizations are welcomed.
        """
        if isinstance( entry, self.model.Library ):
            return self.check_folder_contents( user, entry.root_folder )
        elif isinstance( entry, self.model.LibraryFolderDatasetAssociation ):
            return self.allow_action( user, self.permitted_actions.DATASET_ACCESS, dataset=entry )
        elif isinstance( entry, self.model.LibraryFolder ):
            for dataset in entry.active_datasets:
                if self.allow_action( user, self.permitted_actions.DATASET_ACCESS, dataset=dataset ):
                    return True
            for folder in entry.active_folders:
                if self.check_folder_contents( user, folder ):
                    return True
            return False
        else:
            raise 'Passed an illegal object to check_folder_contents: %s' % type( entry )

def get_permitted_actions( self, filter=None ):
    '''Utility method to return a subset of RBACAgent's permitted actions'''
    if filter is None:
        return RBACAgent.permitted_actions
    if not filter.endswith('_'):
        filter += '_'
    tmp_bunch = Bunch()
    [tmp_bunch.__dict__.__setitem__(k, v) for k, v in RBACAgent.permitted_actions.items() if k.startswith(filter)]
    return tmp_bunch
