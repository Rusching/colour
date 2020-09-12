# -*- coding: utf-8 -*-
"""
Otsu et al. (2018) - Reflectance Recovery
=========================================

Defines objects for reflectance recovery, i.e. spectral upsampling, using
*Otsu et al. (2018)* method:

-   :class:`colour.recovery.Dataset_Otsu2018`
-   :func:`colour.recovery.XYZ_to_sd_Otsu2018`
-   :func:`colour.recovery.NodeTree_Otsu2018`

References
----------
-   :cite:`Otsu2018` : Otsu, H., Yamamoto, M., & Hachisuka, T. (2018).
    Reproducing Spectral Reflectances From Tristimulus Colours. Computer
    Graphics Forum, 37(6), 370–381. doi:10.1111/cgf.13332
"""

from __future__ import division, print_function, unicode_literals

import numpy as np
import six
from collections import namedtuple

from colour.colorimetry import (MSDS_CMFS_STANDARD_OBSERVER,
                                SpectralDistribution, SpectralShape,
                                msds_to_XYZ, sd_to_XYZ, sd_ones)
from colour.models import XYZ_to_xy
from colour.recovery import (SPECTRAL_SHAPE_OTSU2018, BASIS_FUNCTIONS_OTSU2018,
                             CLUSTER_MEANS_OTSU2018, SELECTOR_ARRAY_OTSU2018)
from colour.utilities import as_float_array, interval, zeros, is_tqdm_installed

if six.PY3:
    from unittest import mock
else:
    import mock
if is_tqdm_installed():
    from tqdm import tqdm
else:
    tqdm = mock.MagicMock()

__author__ = 'Colour Developers'
__copyright__ = 'Copyright (C) 2013-2020 - Colour Developers'
__license__ = 'New BSD License - https://opensource.org/licenses/BSD-3-Clause'
__maintainer__ = 'Colour Developers'
__email__ = 'colour-developers@colour-science.org'
__status__ = 'Production'

__all__ = ['Dataset_Otsu2018', 'XYZ_to_sd_Otsu2018', 'NodeTree_Otsu2018']


class Dataset_Otsu2018(object):
    """
    Stores all the information needed for the *Otsu et al. (2018)* spectral
    upsampling method.

    Datasets can be either generated and converted as a
    :class:`colour.recovery.Dataset_Otsu2018` class instance using the
    :meth:`colour.recovery.NodeTree_Otsu2018.to_dataset` method or
    alternatively, loaded from disk with the
    :meth:`colour.recovery.Dataset_Otsu2018.read` method.

    Parameters
    ----------
    shape: SpectralShape
        Shape of the spectral data.
    basis_functions : array_like, (n, 3, m)
        Three basis functions for every cluster.
    means : array_like, (n, m)
        Mean for every cluster.
    selector_array : array_like, (k, 4)
        Array describing how to select the appropriate cluster. See
        :meth:`colour.recovery.Dataset_Otsu2018.select` method for details.

    Attributes
    ----------
    shape
    basis_functions
    means
    selector_array

    Methods
    -------
    write
    read
    select
    cluster
    """

    def __init__(self,
                 shape=None,
                 basis_functions=None,
                 means=None,
                 selector_array=None):
        self._shape = shape
        self._basis_functions = basis_functions
        self._means = means
        self._selector_array = selector_array

    @property
    def shape(self):
        """
        Getter property for the shape used by the *Otsu et al. (2018)* dataset.

        Returns
        -------
        SpectralShape
            Shape used by the *Otsu et al. (2018)* dataset.
        """

        return self._shape

    @property
    def basis_functions(self):
        """
        Getter property for the basis functions of the *Otsu et al. (2018)*
        dataset.

        Returns
        -------
        ndarray
            Basis functions of the *Otsu et al. (2018)* dataset.
        """

        return self._basis_functions

    @property
    def means(self):
        """
        Getter property for means of the *Otsu et al. (2018)* dataset.

        Returns
        -------
        int
            Means of the *Otsu et al. (2018)* dataset.
        """

        return self._means

    @property
    def selector_array(self):
        """
        Getter property for the selector array of the *Otsu et al. (2018)*
        dataset.

        Returns
        -------
        ndarray
            Selector array of the *Otsu et al. (2018)* dataset.
        """

        return self._selector_array

    def __str__(self):
        """
        Returns a formatted string representation of the dataset.

        Returns
        -------
        unicode
            Formatted string representation.
        """

        return '{0}({1} basis functions)'.format(
            self.__class__.__name__, self._basis_functions.shape[0])

    def write(self, path):
        """
        Writes the dataset to an *.npz* file at given path.
        """

        shape_array = as_float_array(
            [self._shape.start, self._shape.end, self._shape.interval])

        np.savez(
            path,
            shape=shape_array,
            basis_functions=self._basis_functions,
            means=self._means,
            selector_array=self._selector_array)

    def read(self, path):
        """
        Reads and loads a dataset from an *.npz* file.

        Parameters
        ----------
        path : unicode
            Path to file.

        Raises
        ------
        ValueError, KeyError
            Raised when loading the file succeeded but it did not contain the
            expected data.
        """

        npz = np.load(path)

        if not isinstance(npz, np.lib.npyio.NpzFile):
            raise ValueError('The loaded file is not an ".npz" type file!')

        start, end, interval = npz['shape']
        self._shape = SpectralShape(start, end, interval)
        self._basis_functions = npz['basis_functions']
        self._means = npz['means']
        self._selector_array = npz['selector_array']

        n, three, m = self._basis_functions.shape
        if (three != 3 or self._means.shape != (n, m) or
                self._selector_array.shape[1] != 4):
            raise ValueError(
                'Unexpected array shapes encountered, the file could be '
                'corrupted or in a wrong format!')

    def select(self, xy):
        """
        Returns the cluster index appropriate for the given *CIE xy*
        coordinates.

        Parameters
        ----------
        xy : array_like, (2,)
            *CIE xy* chromaticity coordinates.

        Returns
        -------
        int
            Cluster index.
        """

        i = 0
        while True:
            row = self._selector_array[i, :]
            direction, origin, lesser_index, greater_index = row

            if xy[int(direction)] <= origin:
                index = int(lesser_index)
            else:
                index = int(greater_index)

            if index < 0:
                i = -index
            else:
                return index

    def cluster(self, xy):
        """
        Returns the basis functions and dataset mean for the given *CIE xy*
        coordinates.

        Parameters
        ----------
        xy : array_like, (2,)
            *CIE xy* chromaticity coordinates.

        Returns
        -------
        basis_functions : ndarray, (3, n)
            Three basis functions.
        mean : ndarray, (n,)
            Dataset mean.
        """

        index = self.select(xy)

        return self._basis_functions[index, :, :], self._means[index, :]


DATASET_REFERENCE_OTSU2018 = Dataset_Otsu2018(
    SPECTRAL_SHAPE_OTSU2018, BASIS_FUNCTIONS_OTSU2018, CLUSTER_MEANS_OTSU2018,
    SELECTOR_ARRAY_OTSU2018)
"""
Builtin *Otsu et al. (2018)* dataset as a
:class:`colour.recovery.Dataset_Otsu2018` class instance, usable by
:func:`colour.recovery.XYZ_to_sd_Otsu2018` definition among others.
"""


def XYZ_to_sd_Otsu2018(
        XYZ,
        cmfs=MSDS_CMFS_STANDARD_OBSERVER['CIE 1931 2 Degree Standard Observer']
        .copy().align(SPECTRAL_SHAPE_OTSU2018),
        illuminant=sd_ones(SPECTRAL_SHAPE_OTSU2018),
        dataset=DATASET_REFERENCE_OTSU2018,
        clip=True):
    """
    Recovers the spectral distribution of given *CIE XYZ* tristimulus values
    using *Otsu et al. (2018)* method.

    Parameters
    ----------
    XYZ : array_like, (3,)
        *CIE XYZ* tristimulus values to recover the spectral distribution from.
    cmfs : XYZ_ColourMatchingFunctions, optional
        Standard observer colour matching functions.
    illuminant : SpectralDistribution, optional
        Illuminant spectral distribution.
    dataset : Dataset_Otsu2018, optional
        Dataset to use for reconstruction. The default is to use the published
        data.
    clip : bool, optional
        If *True*, the default, values below zero and above unity in the
        recovered spectral distributions will be clipped. This ensures that the
        returned reflectance is physical and conserves energy, but will cause
        noticeable colour differences in case of very saturated colours.

    Returns
    -------
    SpectralDistribution
        Recovered spectral distribution. Its shape is always that of the
        :class:`colour.recovery.SPECTRAL_SHAPE_OTSU2018` class instance.

    Examples
    --------
    >>> from colour.colorimetry import CCS_ILLUMINANTS, sd_to_XYZ_integration
    >>> from colour.models import XYZ_to_sRGB
    >>> from colour.utilities import numpy_print_options
    >>> XYZ = np.array([0.20654008, 0.12197225, 0.05136952])
    >>> cmfs = (
    ...     MSDS_CMFS_STANDARD_OBSERVER['CIE 1931 2 Degree Standard Observer']
    ... )
    >>> sd = XYZ_to_sd_Otsu2018(XYZ, cmfs)
    >>> with numpy_print_options(suppress=True):
    ...     # Doctests skip for Python 2.x compatibility.
    ...     sd  # doctest: +SKIP
    SpectralDistribution([[ 380.        ,    0.0641416...],
                          [ 390.        ,    0.0617638...],
                          [ 400.        ,    0.0569661...],
                          [ 410.        ,    0.0544889...],
                          [ 420.        ,    0.0545261...],
                          [ 430.        ,    0.0546380...],
                          [ 440.        ,    0.0547425...],
                          [ 450.        ,    0.0529218...],
                          [ 460.        ,    0.0507861...],
                          [ 470.        ,    0.0478568...],
                          [ 480.        ,    0.0457774...],
                          [ 490.        ,    0.0442853...],
                          [ 500.        ,    0.0445246...],
                          [ 510.        ,    0.0441375...],
                          [ 520.        ,    0.0446107...],
                          [ 530.        ,    0.0463802...],
                          [ 540.        ,    0.0480589...],
                          [ 550.        ,    0.0502353...],
                          [ 560.        ,    0.0528937...],
                          [ 570.        ,    0.0614040...],
                          [ 580.        ,    0.0786505...],
                          [ 590.        ,    0.1228663...],
                          [ 600.        ,    0.2068932...],
                          [ 610.        ,    0.3180413...],
                          [ 620.        ,    0.4196476...],
                          [ 630.        ,    0.4871889...],
                          [ 640.        ,    0.5213562...],
                          [ 650.        ,    0.5408883...],
                          [ 660.        ,    0.5532133...],
                          [ 670.        ,    0.5594981...],
                          [ 680.        ,    0.5671239...],
                          [ 690.        ,    0.5741896...],
                          [ 700.        ,    0.5832574...],
                          [ 710.        ,    0.5898516...],
                          [ 720.        ,    0.5957136...],
                          [ 730.        ,    0.6027180...]],
                         interpolator=SpragueInterpolator,
                         interpolator_kwargs={},
                         extrapolator=Extrapolator,
                         extrapolator_kwargs={...})
    >>> sd_to_XYZ_integration(sd) / 100  # doctest: +ELLIPSIS
    array([ 0.2065333...,  0.1219669...,  0.0513723...])
    """

    XYZ = as_float_array(XYZ)
    xy = XYZ_to_xy(XYZ)

    basis_functions, mean = dataset.cluster(xy)

    M = np.empty((3, 3))
    for i in range(3):
        sd = SpectralDistribution(basis_functions[i, :], dataset.shape.range())
        M[:, i] = sd_to_XYZ(sd, cmfs, illuminant) / 100
    M_inverse = np.linalg.inv(M)

    sd = SpectralDistribution(mean, dataset.shape.range())
    XYZ_mu = sd_to_XYZ(sd, cmfs, illuminant) / 100

    weights = np.dot(M_inverse, XYZ - XYZ_mu)
    recovered_sd = np.dot(weights, basis_functions) + mean

    if clip:
        recovered_sd = np.clip(recovered_sd, 0, 1)

    return SpectralDistribution(recovered_sd, dataset.shape.range())


class PartitionAxis(namedtuple('PartitionAxis', ('origin', 'direction'))):
    """
    Represents a horizontal or vertical line, partitioning the 2D space in
    two half-planes.

    Parameters
    ----------
    origin : numeric
        The x coordinate of a vertical line or the y coordinate of a horizontal
        line.
    direction : int
        *0* if vertical, *1* if horizontal.

    Methods
    -------
    __str__
    """

    def __str__(self):
        """
        Returns a formatted string representation of the partition axis.

        Returns
        -------
        unicode
            Formatted string representation.
        """

        return '{0}({1} partition at {2} = {3})'.format(
            self.__class__.__name__, 'horizontal'
            if self.direction else 'vertical', 'y'
            if self.direction else 'x', self.origin)


class ColourData(object):
    """
    Represents the data for multiple colours: their spectral reflectance
    distributions, *CIE XYZ* tristimulus values and *CIE xy* coordinates. The
    standard observer colour matching functions and illuminant are accessed via
    the parent tree.

    This class also supports partitioning: Creating two smaller instances of
    :class:`colour.recovery.otsu2018.ColourData` class by splitting along a
    horizontal or a vertical axis on the *CIE xy* plane.

    Parameters
    ----------
    tree : NodeTree_Otsu2018, optional
        The parent tree which determines the standard observer colour matching
        functions and illuminant used in colourimetric calculations.
    reflectances : ndarray, (n, m), optional
        Reflectances of the *n* colours to be stored in this class. The shape
        must match ``tree.shape`` with *m* points for each colour.

    Attributes
    ----------
    tree
    reflectances
    XYZ
    xy

    Methods
    -------
    __str__
    __len__
    partition
    """

    def __init__(self, tree, reflectances):
        self._tree = tree
        self._XYZ = None
        self._xy = None
        self._reflectances = None
        self.reflectances = reflectances

    @property
    def tree(self):
        """
        Getter property for the colour data tree.

        Returns
        -------
        NodeTree_Otsu2018
            Colour data tree.
        """

        return self._tree

    @property
    def reflectances(self):
        """
        Getter and setter property for the colour data reflectances.

        Parameters
        ----------
        value : array_like
            Value to set the colour data reflectances with.

        Returns
        -------
        ndarray
            Colour data reflectances.
        """

        return self._reflectances

    @reflectances.setter
    def reflectances(self, value):
        """
        Setter for the **self.reflectances** property.
        """

        if value is not None:
            self._reflectances = as_float_array(value)

            wavelengths = self.tree.wavelengths

            self._XYZ = msds_to_XYZ(
                self._reflectances,
                illuminant=self.tree.illuminant,
                method='Integration',
                shape=SpectralShape(
                    np.min(wavelengths),
                    np.max(wavelengths),
                    interval(wavelengths)[0],
                )) / 100
            self._xy = XYZ_to_xy(self._XYZ)

    @property
    def XYZ(self):
        """
        Getter property for the colour data *CIE XYZ* tristimulus values.

        Returns
        -------
        ndarray
            Colour data *CIE XYZ* tristimulus values.
        """

        return self._XYZ

    @property
    def xy(self):
        """
        Getter property for the colour data *CIE xy* tristimulus values.

        Returns
        -------
        ndarray
            Colour data *CIE xy* tristimulus values.
        """

        return self._xy

    def __str__(self):
        """
        Returns a formatted string representation of the colour data.

        Returns
        -------
        unicode
            Formatted string representation.
        """

        return '{0}({1} Reflectances)'.format(self.__class__.__name__,
                                              len(self))

    def __len__(self):
        """
        Returns the number of colours in the colour data.

        Returns
        -------
        int
            Number of colours in the colour data.
        """

        return self._reflectances.shape[0]

    def partition(self, axis):
        """
        Parameters
        ----------
        axis : PartitionAxis
            Partition axis used to partition the colour data.

        Returns
        -------
        lesser : ColourData
            The left or lower part.
        greater : ColourData
            The right or upper part.
        """

        lesser = ColourData(self.tree, None)
        greater = ColourData(self.tree, None)

        mask = self.xy[:, axis.direction] <= axis.origin

        lesser._reflectances = self.reflectances[mask, :]
        greater._reflectances = self.reflectances[~mask, :]

        lesser._XYZ = self.XYZ[mask, :]
        greater._XYZ = self.XYZ[~mask, :]

        lesser._xy = self.xy[mask, :]
        greater._xy = self.xy[~mask, :]

        return lesser, greater


class Node(object):
    """
    Represents a node in a :meth:`colour.recovery.NodeTree_Otsu2018` class
    instance node tree.

    Parameters
    ----------
    tree : NodeTree_Otsu2018
        The parent tree which determines the standard observer colour matching
        functions and illuminant used in colourimetric calculations.
    colour_data : ColourData
        The colour data belonging to this node.

    Attributes
    ----------
    id
    tree
    colour_data
    children
    partition_axis
    basis_functions
    mean
    leaves

    Methods
    -------
    __str__
    __len__
    is_leaf
    split
    PCA
    reconstruct
    leaf_reconstruction_error
    branch_reconstruction_error
    partition_reconstruction_error
    find_best_partition
    """

    _NODE_COUNT = 1
    """
    Total node count.

    _NODE_COUNT : int
    """

    def __init__(self, tree, colour_data):
        self._id = Node._NODE_COUNT
        Node._NODE_COUNT += 1

        self._tree = tree
        self._colour_data = colour_data
        self._children = []
        self._partition_axis = None
        self._mean = None
        self._basis_functions = None

        self._M = None
        self._M_inverse = None
        self._XYZ_mu = None

        self._best_partition = None
        self._cached_leaf_reconstruction_error = None

    @property
    def id(self):
        """
        Getter property for the node id.

        Returns
        -------
        int
            Node id.
        """

        return self._id

    @property
    def tree(self):
        """
        Getter property for the node tree.

        Returns
        -------
        NodeTree_Otsu2018
            Node tree.
        """

        return self._tree

    @property
    def colour_data(self):
        """
        Getter property for the node colour data.

        Returns
        -------
        ColourData
            Node colour data.
        """

        return self._colour_data

    @property
    def children(self):
        """
        Getter property for the node children.

        Returns
        -------
        tuple
            Node children.
        """

        return self._children

    @property
    def partition_axis(self):
        """
        Getter property for the node partition axis.

        Returns
        -------
        PartitionAxis
            Node partition axis.
        """

        return self._partition_axis

    @property
    def basis_functions(self):
        """
        Getter property for the node basis functions.

        Returns
        -------
        array_like
            Node basis functions.
        """

        return self._basis_functions

    @property
    def mean(self):
        """
        Getter property for the node mean distribution.

        Returns
        -------
        array_like
            Node mean distribution.
        """

        return self._mean

    @property
    def leaves(self):
        """
        Getter property for the node leaves.

        Returns
        -------
        generator
            Generator of all the leaves connected to this node.
        """

        if self.is_leaf():
            yield self
        else:
            for child in self._children:
                # TODO: Python 3 "yield from child.leaves".
                for leaf in child.leaves:
                    yield leaf

    def __str__(self):
        """
        Returns a formatted string representation of the node.

        Returns
        -------
        unicode
            Formatted string representation.
        """

        return '{0}#{1}({2})'.format(self.__class__.__name__, self._id,
                                     self._colour_data)

    def __len__(self):
        """
        Returns the number of children of the node.

        Returns
        -------
        int
            Number of children of the node.
        """

        return len(list(self.leaves))

    def is_leaf(self):
        """
        Returns whether the node is a leaf.
        :class:`colour.recovery.NodeTree_Otsu2018` class instance tree leaves
        do not have any children and store instances of
        :class:`colour.recovery.otsu2018.ColourData` class.

        Returns
        -------
        bool
            Whether the node is a leaf.
        """

        return len(self._children) == 0

    def split(self, children, partition_axis):
        """
        Converts the leaf node into a non-leaf node using given children and
        partition axis.

        Parameters
        ----------
        children : tuple
            Tuple of two :class:`colour.recovery.otsu2018.Node` classes
            instances.
        partition_axis : PartitionAxis
            Partition axis.
        """

        self._colour_data = None
        self._children = children
        self._partition_axis = partition_axis

        self._mean = None
        self._basis_functions = None

        self._M = None
        self._M_inverse = None
        self._XYZ_mu = None

        self._best_partition = None
        self._cached_leaf_reconstruction_error = None

    #
    # PCA and Reconstruction
    #

    def PCA(self):
        """
        Performs the *Principal Component Analysis* (PCA) on the colours data
        of the node and sets the relevant private attributes accordingly.

        Raises
        ------
        RuntimeError
            If the node is not a leaf node.
        """

        if not self.is_leaf():
            raise RuntimeError('{0} is not a leaf node!'.format(self))

        if self._M is not None:
            return

        self._mean = np.mean(self._colour_data.reflectances, axis=0)
        self._XYZ_mu = self._tree.msds_to_XYZ(self._mean)

        matrix_data = self._colour_data.reflectances - self._mean
        matrix_covariance = np.dot(np.transpose(matrix_data), matrix_data)
        _eigenvalues, eigenvectors = np.linalg.eigh(matrix_covariance)
        self._basis_functions = np.transpose(eigenvectors[:, -3:])

        self._M = np.transpose(self._tree.msds_to_XYZ(self._basis_functions))
        self._M_inverse = np.linalg.inv(self._M)

    def reconstruct(self, XYZ):
        """
        Reconstructs the reflectance for the given *CIE XYZ* tristimulus
        values.

        If the node is a leaf, the colour data from the node is used, otherwise
        the branch is traversed recursively to find the leaves.

        Parameters
        ----------
        XYZ : ndarray, (3,)
            *CIE XYZ* tristimulus values to recover the spectral distribution
            from.

        Returns
        -------
        SpectralDistribution
            Recovered spectral distribution.
        """

        xy = XYZ_to_xy(XYZ)

        if not self.is_leaf():
            if (xy[self._partition_axis.direction] <=
                    self._partition_axis.origin):
                return self._children[0].reconstruct(XYZ)
            else:
                return self._children[1].reconstruct(XYZ)

        weights = np.dot(self._M_inverse, XYZ - self._XYZ_mu)
        reflectance = np.dot(weights, self._basis_functions) + self._mean
        reflectance = np.clip(reflectance, 0, 1)

        return SpectralDistribution(reflectance, self._tree.wavelengths)

    #
    # Optimisation
    #

    def leaf_reconstruction_error(self):
        """
        Reconstructs the reflectance of the *CIE XYZ* tristimulus values in
        the colour data of this node using PCA and compares the reconstructed
        spectrum against the measured spectrum. The reconstruction errors are
        then summed up and returned.

        Returns
        -------
        error : float
            The reconstruction errors summation for the node.

        Notes
        -----
        The reconstruction error is cached upon being computed and thus is only
        computed once per node.

        Raises
        ------
        RuntimeError
            If the node is not a leaf node.
        """

        if not self.is_leaf():
            raise RuntimeError('{0} is not a leaf node!'.format(self))

        if self._cached_leaf_reconstruction_error:
            return self._cached_leaf_reconstruction_error

        if self._M is None:
            self.PCA()

        error = 0
        for i in range(len(self.colour_data)):
            sd = self.colour_data.reflectances[i, :]
            XYZ = self.colour_data.XYZ[i, :]
            recovered_sd = self.reconstruct(XYZ)
            error += np.sum((sd - recovered_sd.values) ** 2)

        self._cached_leaf_reconstruction_error = error

        return error

    def branch_reconstruction_error(self):
        """
        Computes the reconstruction error for an entire branch of the tree,
        starting from the node, i.e. the reconstruction errors summation for
        all the leaves in the branch.

        Returns
        -------
        error : float
            Reconstruction errors summation for all the leaves in the branch.
        """

        if self.is_leaf():
            return self.leaf_reconstruction_error()
        else:
            return sum([
                child.branch_reconstruction_error() for child in self._children
            ])

    def partition_reconstruction_error(self, axis):
        """
        Computes the reconstruction errors summation of the two nodes created
        by splitting the node with a given partition.

        Parameters
        ----------
        axis : PartitionAxis
            Partition axis used to compute the reconstruction error.

        Returns
        -------
        error : float
            Reconstruction errors summation of the two nodes created
            by splitting the node with a given partition.
        lesser, greater : tuple
            Nodes created by splitting the node with the given partition.
        """

        partition = self.colour_data.partition(axis)

        if (len(partition[0]) < self._tree.minimum_cluster_size or
                len(partition[1]) < self._tree.minimum_cluster_size):
            raise RuntimeError('Partition generated parts smaller '
                               'than the minimum cluster size!')

        lesser = Node(self._tree, partition[0])
        lesser.PCA()

        greater = Node(self._tree, partition[1])
        greater.PCA()

        error = (lesser.leaf_reconstruction_error() +
                 greater.leaf_reconstruction_error())

        return error, (lesser, greater)

    def find_best_partition(self):
        """
        Finds the best partition for the node.

        Returns
        -------
        partition_error : float
            Partition error
        axis : PartitionAxis
            Horizontal or vertical line, partitioning the 2D space in
            two half-planes.
        partition : tuple
            Nodes created by splitting a node with a given partition.
        """

        if self._best_partition is not None:
            return self._best_partition

        leaf_error = self.leaf_reconstruction_error()
        best_error = None

        with tqdm(total=2 * len(self.colour_data)) as progress:
            for direction in [0, 1]:
                for i in range(len(self.colour_data)):
                    progress.update(1)
                    origin = self.colour_data.xy[i, direction]
                    axis = PartitionAxis(origin, direction)

                    try:
                        partition_error, partition = (
                            self.partition_reconstruction_error(axis))
                    except RuntimeError:
                        continue

                    if partition_error >= leaf_error:
                        continue

                    if best_error is None or partition_error < best_error:
                        self._best_partition = (partition_error, axis,
                                                partition)

        if self._best_partition is None:
            raise RuntimeError('Could not find a best partition!')

        return self._best_partition


class NodeTree_Otsu2018(Node):
    """
    A sub-class of :class:`colour.recovery.otsu2018.Node` class representing
    the root node of a tree containing information shared with all the nodes,
    such as the standard observer colour matching functions and the illuminant,
    if any is used.

    Global operations involving the entire tree, such as optimisation and
    reconstruction, are implemented in this sub-class.

    Parameters
    ----------
    reflectances : ndarray, (n, m)
        Reflectances of the *n* reference colours to use for optimisation.
    shape : SpectralShape
        Spectral shape of ``reflectances``.
    cmfs : XYZ_ColourMatchingFunctions, optional
        Standard observer colour matching functions.
    illuminant : SpectralDistribution, optional
        Illuminant spectral distribution.

    Attributes
    ----------
    reflectances
    shape
    cmfs
    illuminant
    minimum_cluster_size

    Methods
    -------
    __str__
    msds_to_XYZ
    optimise
    to_dataset
    """

    def __init__(self,
                 reflectances,
                 shape,
                 cmfs=MSDS_CMFS_STANDARD_OBSERVER[
                     'CIE 1931 2 Degree Standard Observer'],
                 illuminant=sd_ones()):
        self._reflectances = reflectances
        self._shape = shape

        self.wavelengths = self._shape.range()
        self.dw = interval(self.wavelengths)[0]

        self._cmfs = cmfs.copy().align(self._shape)
        self._illuminant = illuminant.copy().align(self._shape)
        # Normalising constant :math:`k`, see :func:`colour.msds_to_XYZ`
        # definition.
        self._k = 1 / (np.sum(
            self._cmfs.values[:, 1] * self._illuminant.values) * self.dw)

        self._minimum_cluster_size = None

        super(NodeTree_Otsu2018, self).__init__(
            self, ColourData(self, self._reflectances))

    @property
    def reflectances(self):
        """
        Getter property for the reflectances.

        Returns
        -------
        ndarray
            Reflectances.
        """

        return self._reflectances

    @property
    def shape(self):
        """
        Getter property for the shape.

        Returns
        -------
        SpectralShape
            Shape.
        """

        return self._shape

    @property
    def cmfs(self):
        """
        Getter property for the standard observer colour matching functions.

        Returns
        -------
        XYZ_ColourMatchingFunctions
            Standard observer colour matching functions.
        """

        return self._cmfs

    @property
    def illuminant(self):
        """
        Getter property for the illuminant.

        Returns
        -------
        SpectralDistribution
            Illuminant.
        """

        return self._illuminant

    @property
    def minimum_cluster_size(self):
        """
        Getter property for the minimum cluster size.

        Returns
        -------
        int
            Minimum cluster size.
        """

        return self._minimum_cluster_size

    def __str__(self):
        """
        Returns a formatted string representation of the tree.

        Returns
        -------
        unicode
            Formatted string representation.
        """

        node_count = len(self)

        return '{0}({1} {2})'.format(self.__class__.__name__, len(self), 'Node'
                                     if node_count == 1 else 'Nodes')

    def _create_selector_array(self):
        """
        Creates an array that describes how to select the appropriate cluster
        for given *CIE xy* coordinates.

        See :meth:`colour.recovery.Dataset_Otsu2018.select` method for
        information about what the array structure and its usage.
        """

        rows = []
        leaf_number = [0]
        symbol_table = {}

        def add_rows(node):
            """
            Add rows for given node and its children.
            """

            if node.is_leaf():
                symbol_table[node] = leaf_number[0]
                leaf_number[0] += 1
                return

            symbol_table[node] = -len(rows)
            rows.append([
                node.partition_axis.direction, node.partition_axis.origin,
                node.children[0], node.children[1]
            ])

            for child in node.children:
                add_rows(child)

        add_rows(self)

        # Special case for tree with just a root node.
        if len(rows) == 0:
            return zeros(4)

        for i, (_direction, _origin, symbol_1, symbol_2) in enumerate(rows):
            rows[i][2] = symbol_table[symbol_1]
            rows[i][3] = symbol_table[symbol_2]

        return as_float_array(rows)

    def msds_to_XYZ(self, reflectances):
        """
        Computes the XYZ tristimulus values of a given reflectance. Faster for
        humans, by using cmfs and the illuminant stored in the ''tree'',
        thus avoiding unnecessary repetition. Faster for computers, by using
        a very simple and direct method.

        Parameters
        ----------
        reflectances : ndarray
            Reflectance with shape matching the one used to construct this
            ``tree``.

        Returns
        -------
        ndarray (3,)
            XYZ tristimulus values, normalised to 1.
        """

        E = self._illuminant.values * reflectances

        return self._k * np.dot(E, self._cmfs.values) * self.dw

    def optimise(self,
                 iterations=8,
                 minimum_cluster_size=None,
                 print_callable=print):
        """
        Optimises the tree by repeatedly performing optimal partitioning of the
        nodes, creating a tree that minimizes the total reconstruction error.

        Parameters
        ----------
        iterations : int, optional
            Maximum number of splits. If the dataset is too small, this number
            might not be reached. The default is to create 8 clusters, like in
            :cite:`Otsu2018`.
        minimum_cluster_size : int, optional
            Smallest acceptable cluster size. By default it is chosen
            automatically, based on the size of the dataset and desired number
            of clusters. It must be at least 3 or the
            *Principal Component Analysis* (PCA) will not be possible.
        print_callable : callable, optional
            Callable used to print progress and diagnostic information.
        """

        self._minimum_cluster_size = (minimum_cluster_size
                                      if minimum_cluster_size is not None else
                                      len(self.colour_data) / iterations // 2)
        self._minimum_cluster_size = max(self._minimum_cluster_size, 3)

        initial_branch_error = self.branch_reconstruction_error()
        print_callable(
            'Initial branch error is: {0:g}.'.format(initial_branch_error))

        best_leaf, best_partition, best_axis, partition_error = [None] * 4

        for i in range(iterations):
            print_callable('\n=== Iteration {0} of {1} ==='.format(
                i + 1, iterations))

            total_error = self.branch_reconstruction_error()
            optimised_total_error = None

            for leaf in self.leaves:
                print_callable('Optimising "{0}"...'.format(leaf))

                try:
                    partition_error, axis, partition = (
                        leaf.find_best_partition())
                except RuntimeError as error:
                    print_callable('Optimisation failed: {0}'.format(error))
                    continue

                new_total_error = (
                    total_error - leaf.leaf_reconstruction_error() +
                    partition_error)

                if (optimised_total_error is None or
                        new_total_error < optimised_total_error):
                    optimised_total_error = new_total_error
                    best_axis = axis
                    best_leaf = leaf
                    best_partition = partition

            if optimised_total_error is None:
                print_callable('\nNo further improvements are possible!\n'
                               'Terminating at iteration {0}.\n'.format(i))
                break

            print_callable(
                '\nSplit "{0}" into "{1}" and "{2}" along "{3}".'.format(
                    best_leaf, best_partition[0], best_partition[1],
                    best_axis))

            print_callable(
                'Error is reduced by {0:g} and is now {1:g}, '
                '{2:.1f}% of the initial error.'.format(
                    leaf.leaf_reconstruction_error() - partition_error,
                    optimised_total_error,
                    100 * optimised_total_error / initial_branch_error))

            best_leaf.split(best_partition, best_axis)

        print_callable('Tree optimisation is complete!')

    def to_dataset(self):
        """
        Creates a :class:`colour.recovery.Dataset_Otsu2018` class instance
        based on data stored in the tree.

        The dataset can then be saved to disk or used to recover reflectance
        with :func:`colour.recovery.XYZ_to_sd_Otsu2018` definition.

        Returns
        -------
        Dataset_Otsu2018
            The dataset object.
        """

        basis_functions = [leaf.basis_functions for leaf in self.leaves]
        means = [leaf.mean for leaf in self.leaves]
        selector_array = self._create_selector_array()

        return Dataset_Otsu2018(self._shape, basis_functions, means,
                                selector_array)
