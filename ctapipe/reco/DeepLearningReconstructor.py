import onnxruntime

import numpy as np
from abc import abstractmethod

from ctapipe.reco.reco_algorithms import Reconstructor

__all__ = ["ONNXModel", "DeepLearningReconstructor"]


class ONNXModel:
    def __init__(self, path):
        try:
            self.sess = onnxruntime.InferenceSession(path)
        except RuntimeError:
            raise ValueError(f'The model could not be loaded from "{path}"')

    def predict(self, *args, **kwargs):
        """
        Start a prediction using the given inputs

        Parameters
        ----------
        *args
            Ordered arguments to use as inputs (will be automatically assigned to
            each model input)
        **kwargs
            Named arguments to use as inputs
        Returns
        -------
        list
            List with the predictions of each output
        """
        n_inputs = len(self.inputs)
        if len(kwargs) == 0 and len(args) == 0:
            raise ValueError(
                "The number of given (named xor ordered) arguments must be at least 1"
            )
        if len(kwargs) != 0 and len(args) != 0:
            raise ValueError(
                "Ordered arguments and named arguments can't be given in the same "
                "prediction"
            )
        if len(kwargs) != n_inputs and len(args) != n_inputs:
            raise ValueError(
                f"The number of given arguments ({max(len(kwargs), len(args))}) must be "
                f"equal to the number of model inputs ({n_inputs})"
            )
        if len(args) != 0:
            for i in range(n_inputs):
                kwargs[self.inputs[i].name] = args[i]

        n_predictions = [len(kwargs[name]) for name in kwargs]
        if len(set(n_predictions)) != 1:
            raise ValueError("All inputs must have the same length")

        for name in kwargs:
            inp = kwargs[name]
            # to avoid common type errors, convert arrays with
            # dtype float64 to float32 (as ONNX only supports the latter)
            if isinstance(inp, np.ndarray) and inp.dtype == np.float64:
                kwargs[name] = inp.astype(np.float32)
        return self.sess.run(None, kwargs)

    @property
    def inputs(self):
        """
        Inputs as returned by the ONNX model

        Returns
        -------
        list
            List of ONNX inputs from the model
        """
        return self.sess.get_inputs()

    @property
    def outputs(self):
        """
        Outputs as returned by the ONNX model

        Returns
        -------
        list
            List of ONNX outputs from the model
        """
        return self.sess.get_outputs()


class DeepLearningReconstructor(Reconstructor):
    """
    Base class for techniques that use Deep Learning to reconstruct the direction and/or
    energy of an atmospheric shower using one or more ONNX models (neural networks).
    It transforms each event observation to the data used by the model and combines the
    outputs into a ReconstructedShowerContainer.

    Attributes
    ----------
    models_paths : Dict[str, str]
        dictionary with cam name as key and
        ONNX model file path as value
    """

    def __init__(self, models_paths, config=None, parent=None, **kwargs):
        self.models = {
            cam_name: ONNXModel(path) for (cam_name, path) in models_paths.items()
        }
        not_supported_cams = [
            cam_name
            for cam_name in self.models.keys()
            if cam_name not in self.supported_cameras
        ]
        if len(not_supported_cams) > 0:
            raise ValueError(
                f"Some of the given camera names are not supported by "
                f"this reconstructor: "
                f"{', '.join(not_supported_cams)}"
            )
        super().__init__(config=config, parent=parent, **kwargs)

    @property
    @abstractmethod
    def supported_cameras(self):
        """
        Cameras supported by this reconstructor

        Returns
        -------
        List[str]
            List of camera names supported by this reconstructor
        """

    def predict(self, tels_dict, subarray, **kwargs):
        """
        Start a prediction using the given models and then combine
        all the observations into a ReconstructedShowerContainer

        Parameters
        ----------
        tels_dict : dict
            dictionary with telescope IDs as key and
            the input as value
        Returns
        -------
        ctapipe.containers.ReconstructedShowerContainer
            The shower container with the reconstructed data
        """
        predictions = dict()
        for cam_name in self.supported_cameras:
            models_path = self.models.get(cam_name)
            if models_path is None:
                continue

            model = self._get_model(cam_name)

            obs_inputs = [
                tels_dict[tel_id]
                for tel_id in tels_dict
                if subarray.tel[tel_id].camera.geometry.camera_name == cam_name
            ]

            predictions[cam_name] = list()
            for inp in obs_inputs:
                if isinstance(inp, list):
                    predictions[cam_name].append(model.predict(*inp))
                elif isinstance(inp, dict):
                    predictions[cam_name].append(model.predict(**inp))
                else:
                    predictions[cam_name].append(model.predict(inp))
        return self._reconstruct(predictions)

    def _get_model(self, cam_name):
        """
        Return an instance of a ONNXModel that corresponds to the given camera name.

        Parameters
        ----------
        cam_name : str
            Camera name which the returned model can process (e.g.
            FlashCam, ASTRICam, LSTCam, etc.)

        Returns
        -------
        model : List[ONNXModel]
            List of events to be used for training
        """
        return self.models[cam_name]

    @abstractmethod
    def _reconstruct(self, models_outputs):
        """
        Method to convert the model outputs for one event to
        a container with the reconstructed shower.

        Parameters
        ----------
        models_outputs : Dict[str, List[Any]]
            dictionary with camera name as key and
            a list of model outputs as value

        Returns
        -------
        ReconstructedShowerContainer
            Reconstructed shower container made from the models' outputs
        """